import json
import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import authentication_classes, permission_classes
from django.db import transaction
from urllib.parse import quote, unquote

from ..utils.GraphDBManager import GraphDBManager
from ..models import VocabularyMapping

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

def mint_uri_like_dataset(dataset_iri: str, short_label: str) -> str:
    """Generate a new URI based on the dataset IRI and a short label provided by the user."""
    base = dataset_iri.split('#', 1)[0] 
    return f"{base}#{slugify_label(short_label)}"

def list_dataset_properties(user_id: int, dataset_iri: str):
    g = GraphDBManager(user_id=user_id)
    ds = (dataset_iri or "").strip().strip("<>")
    collection_iri = f"{ds}/collection"  

    sparql_pattern = f"""
        <{collection_iri}> ?_ ?feature .
        ?feature ?uri ?o .
        FILTER (?uri != rdf:type)
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
        details = []

        with transaction.atomic():
            for idx, it in enumerate(items, start=1):
                if not isinstance(it, dict):
                    details.append({"index": idx, "status": "skipped", "reason": "not an object"})
                    continue

                uri = (it.get("original_uri") or it.get("uri") or "").strip().strip("<>")

                new_label = (it.get("new_label") or "").strip()

                if new_label == "":
                    VocabularyMapping.objects.filter(
                        user=request.user,
                        dataset_iri=dataset,
                        original_uri=uri,
                    ).delete()
                    details.append({"index": idx, "status": "deleted", "uri": uri})
                    continue

                new_uri = mint_uri_like_dataset(dataset, new_label)

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

        return Response({"saved": saved, "details": details}, status=status.HTTP_200_OK)
