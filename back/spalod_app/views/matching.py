from email.mime import text
import json
import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import authentication_classes, permission_classes
from django.db import transaction
from urllib.parse import quote, unquote, urlparse
import requests
from rdflib import RDF, Graph, URIRef
from rdflib.namespace import SKOS, DCTERMS
from rdflib.namespace import RDFS, OWL

from ..utils.GraphDBManager import GraphDBManager
from ..models import VocabularyMapping , UserVocabulary
from spalod_app.utils.uskb import resolve_schema_uri_by_label , get_property_terms

FIXED_PREFIX = "https://geovast3d.com/ontologies/spalod#"

def label_from_uri(u: str) -> str:
    """Extract the label part from a URI (e.g. '...#name' → 'name')."""
    if not u:
        return ""
    frag = u.split('#', 1)[-1] if '#' in u else u.rstrip('/').split('/')[-1]
    try:
        return unquote(frag)
    except Exception:
        return frag

def slugify_label(label: str) -> str:
    """Convert a label into a URI-safe format."""
    s = re.sub(r'\s+', '-', label.strip())
    return quote(s, safe='-._~')

def list_dataset_properties(user_id: int, dataset_iri: str):
    g = GraphDBManager(user_id=user_id)
    ds = (dataset_iri or "").strip().strip("<>")
    collection_iri = f"{ds}/collection"  

    sparql_pattern = f"""
        <{collection_iri}> ?_ ?feature .
        ?feature ?uri ?o .
        FILTER (STRSTARTS(STR(?uri), "https://geovast3d.com/ontologies/spalod#"))
        OPTIONAL {{ ?uri rdfs:label ?l }}
        BIND( COALESCE(?l, STRAFTER(STR(?uri), "#")) AS ?name )
    """

    res = g.query_graphdb(sparql_pattern)

    seen, items = set(), []
    for b in res.get("results", {}).get("bindings", []):
        uri = b.get("uri", {}).get("value")
        name = b.get("name", {}).get("value")
        if not uri or uri in seen:
            continue
        seen.add(uri)
        items.append({"uri": uri, "label": name or uri})
    items.sort(key=lambda x: x["label"].lower())
    return items

def to_list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            j = json.loads(v)
            return j if isinstance(j, list) else []
        except Exception:
            return []
    return []

def get_label(g: Graph, s: URIRef, p: URIRef):
    for o in g.objects(s, p):
        txt = str(o).strip()
        if txt:
            return txt
    return None

def normalize_github_raw_url(url: str) -> str:
    url = (url or "").strip()
    if "github.com/" in url and "/blob/" in url:
        url = url.replace("github.com/", "raw.githubusercontent.com/").replace("/blob/", "/")
    return url

def extract_terms_from_ttl_url(url: str):

    url =normalize_github_raw_url(url)

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    g = Graph()
    g.parse(data=resp.text, format="turtle")
    # print("TTL triples:", len(g))

    terms = []

    for s in set(g.subjects()):
        if not isinstance(s, URIRef):
            continue

        uri = str(s).strip()
        if not uri :
            continue

        if (s, RDF.type, OWL.Ontology) in g:
            continue

        # 1) rdfs:label
        label = get_label(g, s, RDFS.label)

        # 2) skos:prefLabel
        if not label:
            label = get_label(g, s, SKOS.prefLabel)
        # 3) dcterms:title
        if not label:
            label = get_label(g, s, DCTERMS.title)

        # 4) fallback to URI
        if not label:
            label = label_from_uri(uri)

        if label:
            terms.append({"label": label, "uri": uri})

    terms.sort(key=lambda x: x["label"].lower())
    return terms

def detect_vocab_kind(url: str) -> str | None:
    """
    Returns 'ttl' or 'json' if supported, otherwise None.
    """
    base = url.lower().split("?", 1)[0]
    if base.endswith(".ttl"):
        return "ttl"
    if base.endswith(".json"):
        return "json"
    return None

def title_from_vocab_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    last = path.rstrip("/").split("/")[-1] if path else ""

    name = unquote(last).strip()

    for ext in (".ttl", ".json"):
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break

    if not name:
        name = parsed.netloc

    name = name.replace("_", " ").replace("-", " ").strip()

    return name.title()

@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
class MatchingDatasetsView(APIView):
    """Returns a list of all datasets available in GraphDB."""

    def get(self, request, *args, **kwargs):
        g = GraphDBManager(user_id=request.user.id)
        sparql_pattern = """
            ?dataset a <http://www.w3.org/ns/dcat#Dataset> .
            OPTIONAL { ?dataset <http://purl.org/dc/terms/title> ?title }
            OPTIONAL { ?dataset <http://www.w3.org/2000/01/rdf-schema#label> ?label }
            """
        
        results = g.query_graphdb(sparql_pattern)
        bindings = results if isinstance(results, list) else results.get("results", {}).get("bindings", [])
        items = []
        for b in bindings:
            iri   = b.get("dataset", {}).get("value")
            title = b.get("title", {}).get("value") if b.get("title") else None
            label = b.get("label", {}).get("value") if b.get("label") else None
            if iri:
                tail = iri.rsplit("#", 1)[-1] if "#" in iri else iri.rsplit("/", 1)[-1]
                items.append({"iri": iri, "label": title or label or tail})

        return Response({"datasets": items}, status=status.HTTP_200_OK)


@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
class MatchingPropertiesView(APIView):
    """
    Returns all dataset properties, merged with user-specific mappings
    stored in the VocabularyMapping model.
    """

    def build_response(self, request, dataset: str):
        if not dataset:
            return Response({"error": "Missing dataset"}, status=status.HTTP_400_BAD_REQUEST)

        dataset = dataset.strip().strip("<>") 
        props = list_dataset_properties(request.user.id, dataset)

        mappings = VocabularyMapping.objects.filter(user=request.user, dataset_iri=dataset)
        map_dict = {m.original_uri: (m.new_uri or "") for m in mappings}

        def tail(iri: str) -> str:
            return iri.rsplit("#", 1)[-1] if "#" in iri else iri.rsplit("/", 1)[-1]

        data = []
        for p in props:
            uri = p["uri"]
            orig_label = p.get("label") or tail(uri)
            mapped_short = label_from_uri(map_dict.get(uri, ""))
            display = mapped_short or orig_label

            data.append({
                "uri": uri,
                "original_label": orig_label,   
                "mapped_label": mapped_short,         
                "display_label": display,      
                "mapped_uri": map_dict.get(uri, "") or None,      
            })

        data.sort(key=lambda x: x["display_label"].lower())
        return Response({"properties": data}, status=status.HTTP_200_OK)

    def get(self, request, *args, **kwargs):
        dataset = (request.query_params.get("dataset") or "").strip()
        return self.build_response(request, dataset)
    
    

@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
class MatchingMappingsView(APIView):
    """
    Saves or updates user-provided vocabulary mappings for a given dataset.
    """

    def post(self, request, *args, **kwargs):
        payload = request.data

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                return Response({"error": "Body must be valid JSON"}, status=status.HTTP_400_BAD_REQUEST)

        dataset = (payload.get("dataset") or "").strip().strip("<>")
        raw_items = payload.get("items", [])
        items = to_list(raw_items)

        if not dataset:
            return Response({"error": "dataset is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not items:
            return Response({"error": "items must be a non-empty JSON array"}, status=status.HTTP_400_BAD_REQUEST)

        saved = 0
        deleted = 0
        details = []

        with transaction.atomic():
            for idx, it in enumerate(items, start=1):
                if not isinstance(it, dict):
                    details.append({"index": idx, "status": "skipped", "reason": "not an object"})
                    continue

                uri = (it.get("original_uri") or it.get("uri") or "").strip().strip("<>")
                new_label = (it.get("new_label") or "").strip()
                source = (it.get("source") or "").strip().lower()

                if new_label == "":
                    VocabularyMapping.objects.filter(
                        user=request.user,
                        dataset_iri=dataset,
                        original_uri=uri,
                    ).delete()
                    deleted += 1
                    details.append({"index": idx, "status": "deleted", "uri": uri})
                    continue

                if source == "schema.org":
                    try:
                        resolved = resolve_schema_uri_by_label(new_label)
                    except Exception:
                        resolved = None
                    new_uri = resolved or f"{FIXED_PREFIX}{slugify_label(new_label)}"
                else:
                    text = new_label.strip()
                    low = text.lower()
                    
                    if low.startswith("http://") or low.startswith("https://"):
                        new_uri = text.strip("<>")
                    else:
                        new_uri = f"{FIXED_PREFIX}{slugify_label(new_label)}"

                obj, created = VocabularyMapping.objects.update_or_create(
                    user=request.user,
                    dataset_iri=dataset,
                    original_uri=uri,
                    defaults={"new_uri": new_uri[:500]},
                )
                saved += 1
                details.append({
                    "index": idx,
                    "status": "saved" if created else "updated",
                    "uri": uri,
                    "new_uri": new_uri
                })

        return Response({"saved": saved, "deleted": deleted, "total": saved + deleted, "details": details}, status=status.HTTP_200_OK)
    

@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])        
class SchemaOrgTerms(APIView):
    """Returns schema.org property terms for autocomplete (cached)."""

    def get(self, request):
        q = (request.GET.get("q") or "").strip()
        limit = int(request.GET.get("limit") or 1000)

        try:
            terms = get_property_terms(q=q, limit=limit)
            return Response({"terms": terms}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
class ExternalVocabularyTerms(APIView):
    """Fetches and returns terms from a vocabulary provided via URL."""

    def get(self, request):
        url = (request.GET.get("url") or "").strip()
        q = (request.GET.get("q") or "").strip().lower()

        if not url:
            return Response(
                {"error": "Missing 'url' parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if url.lower().split("?", 1)[0].endswith(".ttl"):
            try:
                terms = extract_terms_from_ttl_url(url)
                return Response({"terms": terms}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return Response(
                {"error": f"Failed to fetch codelist: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        codelist = data.get("codelist") or {}
        items = []
        for item in codelist.get("containeditems", []):
            v = item.get("value") or {}
            lbl_obj = v.get("label") or {}
            label = lbl_obj.get("text") or ""
            uri = v.get("id") or v.get("latestversion")

            if not label or not uri:
                continue

            if q and q not in label.lower():
                continue

            items.append(
                {
                    "label": label,
                    "uri": uri,
                }
            )

        items.sort(key=lambda x: x["label"].lower())
        return Response({"terms": items}, status=status.HTTP_200_OK)


@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
class UserVocabularies(APIView):
    """Returns the list of vocabularies saved by the current user."""

    def get(self, request):
        rows = (
            UserVocabulary.objects
            .filter(user=request.user)
            .values("id", "title", "url", "created_at")
            .order_by("created_at")
        )
        return Response({"vocabularies": list(rows)}, status=status.HTTP_200_OK)
    def post(self, request):
        url = (request.data.get("url") or "").strip()
        title = (request.data.get("title") or "").strip()

        if not url:
            return Response({"error": "Missing 'url' field"}, status=status.HTTP_400_BAD_REQUEST)
        
        url = normalize_github_raw_url(url)

        kind = detect_vocab_kind(url)
        if not kind:
            return Response(
                {"error": "Only .ttl and .json vocabularies are supported right now."},
                status=status.HTTP_400_BAD_REQUEST,
            )


        derived_title = title_from_vocab_url(url)
        final_title = title or derived_title

 
        obj, created = UserVocabulary.objects.get_or_create(
            user=request.user,
            url=url,
            defaults={"title": final_title},
        )
        if not created and title and (obj.title != title):
            obj.title = title
            obj.save(update_fields=["title"])

        payload = {
            "id": obj.id,
            "title": obj.title,
            "url": obj.url,
        }

        return Response(
            payload,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
