from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import os
import json
import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import threading
import requests
import gzip
import json, re, uuid
import io, zipfile, tempfile, shutil
from pathlib import Path
import geopandas as gpd
from shapely.geometry import mapping, shape
from pyproj import Transformer
import html
import xml.etree.ElementTree as ET

from ..serializers import UploadedFileSerializer
from ..utils.GraphDBManager import validate_geojson_file,GraphDBManager

MAX_CHUNK_SIZE = 50 * 1024 * 1024 
SAFE_RE = re.compile(r'[^A-Za-z0-9_-]')
META_EPSG_LAGE_PAT = re.compile(r"EPSG[-\s]*Code\s*Lage\s*:\s*(\d+)", re.IGNORECASE)

def sanitize_key(k: str) -> str:
    """Normalize a property name to a JSON/JS-friendly, RDF-safe identifier."""
    s = SAFE_RE.sub('_', str(k))
    if not re.match(r'^[A-Za-z_]', s):
        s = f"p_{s}"
    s = re.sub(r'_+', '_', s).strip('_')
    return s

def make_safe_columns(gdf):
    """Apply sanitize_key to all non-geometry columns."""
    cols = []
    for c in gdf.columns:
        cols.append(c if c == "geometry" else sanitize_key(c))
    gdf2 = gdf.copy()
    gdf2.columns = cols
    return gdf2


def drop_z_if_nan(geom):
    """Remove Z when it is NaN, keep XY as-is, recurse through coordinate arrays."""
    try:
        coords = mapping(geom)["coordinates"]

        def clean(c):
            if isinstance(c, (list, tuple)) and c and isinstance(c[0], (float, int)):
                # [x, y] or [x, y, z]
                if len(c) == 3 and (c[2] != c[2]):  # NaN check
                    return [c[0], c[1]]
                return list(c)
            if isinstance(c, (list, tuple)):
                return [clean(x) for x in c]
            return c

        new_geom = {"type": geom.geom_type, "coordinates": clean(coords)}
        return shape(new_geom)
    except Exception:
        return None
    
def is_gml_featurecollection_empty(path: str) -> bool:

    """Return True if the GML FeatureCollection has zero members."""
    try:
        for event, elem in ET.iterparse(path, events=("start",)):
            tag = elem.tag.split('}')[-1]  # strip namespace
            if tag in ("member", "featureMember"):
                return False
        return True
    except ET.ParseError:
        return False
    
def extract_and_find(zip_path: str, kind: str):
    """
    extract a ZIP to a temp dir and return paths based on kind.
    kind ∈ {"shp", "xyz"}
    """
    tmpdir = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmpdir)

        if kind == "shp":
            shp_list = list(tmpdir.rglob("*.shp"))
            shp = shp_list[0]
            base = shp.with_suffix("")
            sidecars = {p.suffix.lower() for p in shp.parent.glob(base.name + ".*")}
            missing = {".shx", ".dbf"} - sidecars
            if missing:
                raise ValueError(f"Missing Shapefile sidecars: {', '.join(sorted(missing))}")
            return tmpdir, shp

        if kind == "xyz":
            xyz_list = list(tmpdir.rglob("*.xyz"))
            xyz = xyz_list[0]
            meta = xyz.with_suffix(".meta")
            return tmpdir, xyz, (meta if meta.exists() else None)

        raise ValueError("Unsupported kind; use 'shp' or 'xyz'.")

    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

def parse_epsg_from_meta(meta_path: Path):
    """Return horizontal EPSG from a .meta file (or None if not present)."""
    try:
        text = Path(meta_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    m = META_EPSG_LAGE_PAT.search(text)
    return int(m.group(1)) if m else None

def remove_html_tags(path: str, keys: tuple = ()):
    """
    Remove simple HTML from feature properties.
    """
    rx_tag = re.compile(r'<[^>]+>')

    def clean(s: str) -> str:
        s = rx_tag.sub(' ', s)
        return html.unescape(s).strip()

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for feat in data.get('features', []):
        props = feat.get('properties', {})
        for k, v in list(props.items()):
            if isinstance(v, str) and (not keys or k in keys):
                props[k] = clean(v)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

def convert_gml_to_geojson(in_path: str, out_path: str) -> None:
    """
    Read GML, clean geometries, reproject to WGS84 (EPSG:4326), sanitize columns,
    and write GeoJSON.
    """
    gdf = gpd.read_file(in_path)

    gdf["geometry"] = gdf["geometry"].apply(drop_z_if_nan)
    gdf = gdf[~gdf.geometry.isnull()]

    gdf = gdf.to_crs(epsg=4326)
    gdf = make_safe_columns(gdf)


    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GeoJSON")

    gfs = Path(in_path).with_suffix('.gfs')
    if gfs.exists():
        try:
            gfs.unlink()
        except Exception:
            pass

def convert_shapefile_zip_to_geojson(zip_path: str, out_geojson_path: str) -> None:
    """
    Convert a Shapefile contained in a ZIP to GeoJSON (EPSG:4326).
    Cleans geometries (drop Z=NaN, remove nulls).
    """
    tmpdir, shp = extract_and_find(zip_path, "shp")
    try:
        gdf = gpd.read_file(shp)

        gdf["geometry"] = gdf["geometry"].apply(drop_z_if_nan)
        gdf = gdf[~gdf.geometry.isnull()]

        gdf = gdf.to_crs(epsg=4326)
        gdf = make_safe_columns(gdf)

        Path(out_geojson_path).parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(out_geojson_path, driver="GeoJSON")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def convert_xyz_to_geojson_core(xyz_path: str, out_geojson_path: str,
                      meta: Path | None, fallback_src_epsg: str = "EPSG:25832") -> None:
    """
    Convert a .xyz to GeoJSON in WGS84 (EPSG:4326).
    Uses EPSG from .meta if present, otherwise a default.
    """
    epsg = parse_epsg_from_meta(meta) if meta else None
    src_epsg = f"EPSG:{epsg}" if epsg else fallback_src_epsg
    transformer = Transformer.from_crs(src_epsg, "EPSG:4326", always_xy=True)

    Path(out_geojson_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_geojson_path, "w", encoding="utf-8") as dst, \
         open(xyz_path, "r", encoding="utf-8", errors="ignore") as src:
        dst.write('{"type":"FeatureCollection","features":[')
        first = True
        for line in src:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                lon, lat = transformer.transform(x, y)
            except Exception:
                continue

            feature = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"x": x, "y": y, "z": z},
            }
            if not first:
                dst.write(",")
            dst.write(json.dumps(feature, ensure_ascii=False, separators=(",", ":")))
            first = False
        dst.write("]}")


def convert_xyz_or_zip_to_geojson(path: str, out_geojson_path: str,
                           fallback_src_epsg: str = "EPSG:25832") -> None:
    """Convert a .xyz or a .zip containing .xyz to GeoJSON (EPSG:4326)."""

    if str(path).lower().endswith(".zip"):
        tmpdir, xyz_path, meta = extract_and_find(path, "xyz")
        try:
            convert_xyz_to_geojson_core(xyz_path, out_geojson_path, meta, fallback_src_epsg)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    else:
        convert_xyz_to_geojson_core(path, out_geojson_path, None, fallback_src_epsg)


class FileUploadView(APIView):
    def post(self, request, *args, **kwargs):
        print("::::::: FileUploadView :::::::")
        file = request.FILES.get('file')  # Access the file
        metadata = request.data.get('metadata')  # Access the metadata as JSON
        user_id = request.user.id
        print(f"Uploading file for User ID: {user_id}")
        if not file or not metadata:
            return Response({'error': f'File and metadata are required: file {file} ; metadata {metadata}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            metadata = json.loads(metadata)
        except ValueError:
            return Response({'error': 'Invalid JSON for metadata.'}, status=status.HTTP_400_BAD_REQUEST)
        
        
        file_uuid = str(uuid.uuid4())

        upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', file_uuid)

        os.makedirs(upload_dir, exist_ok=True)
        print("MEDIA_ROOT =", settings.MEDIA_ROOT)

         # Extract the original file extension
        file_extension = os.path.splitext(file.name)[1] .lower()
        try:
            file_path = os.path.join(upload_dir, f'{file_uuid}{file_extension}')
            original_url = f'/media/uploads/{file_uuid}/{file_uuid}{file_extension}'

             # Save the file to the constructed path
            with open(file_path, 'wb') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)
            # ontology_file_path = os.path.join(upload_dir, f'{file_uuid}_ontology.owl')
            # ontology_url = f'/media/uploads/{file_uuid}/{file_uuid}_ontology.owl'
           
            try:
                print("[INFO] Read Metadata")
                catalog_name = metadata.get("catalog")
                dataset_name = metadata.get("title")
                # Normalize catalog and dataset names to make valid URIs (replace spaces, dots, dashes)
                catalog_name = re.sub(r"[ .-]", "_", catalog_name)
                dataset_name = re.sub(r"[ .-]", "_", dataset_name)
                graph_manager = GraphDBManager(user_id)

                catalog_uri, dataset_uri = graph_manager.initialize_dataset_structure(catalog_name,dataset_name)
                triples_added = graph_manager.add_dcterms_metadata_to_dataset(dataset_uri,metadata)
                print(f"✅ Added {len(triples_added)} DCTERMS metadata triples.")
                # processor = OntologyProcessor(file_uuid, ontology_url, original_url,metadata,user_id)

                if file_extension == ".zip":
                    print("[INFO] Converting ZIP to GeoJSON…")
                    geojson_path = os.path.join(upload_dir, f"{file_uuid}.geojson")

                    try:
                        convert_shapefile_zip_to_geojson(file_path, geojson_path)
                    except Exception:
                        try:
                            convert_xyz_or_zip_to_geojson(file_path, geojson_path, fallback_src_epsg="EPSG:25832")
                        except Exception:
                            graph_manager.delete_all(str(dataset_uri))
                            shutil.rmtree(upload_dir, ignore_errors=True)
                            return Response(
                                {'error': 'ZIP must contain a Shapefile (.shp + .dbf + .shx) or .xyz'},
                                status=status.HTTP_400_BAD_REQUEST
                            )

                    file_path = geojson_path
                    original_url = f'/media/uploads/{file_uuid}/{file_uuid}.geojson'
                    file_extension = ".geojson" 

                elif file_extension == '.xyz':
                    print("[INFO] Converting raw XYZ to GeoJSON…")
                    geojson_path = os.path.join(upload_dir, f"{file_uuid}.geojson")
                    convert_xyz_or_zip_to_geojson(file_path, geojson_path, fallback_src_epsg="EPSG:25832")
                    file_path = geojson_path
                    original_url = f'/media/uploads/{file_uuid}/{file_uuid}.geojson'
                    file_extension = ".geojson" 
                
                elif file_extension == ".gml":
                    print("[INFO] Converting GML to GeoJSON…")
                    if is_gml_featurecollection_empty(file_path):
                        graph_manager.delete_all(str(dataset_uri))
                        shutil.rmtree(upload_dir, ignore_errors=True)
                        return Response(
                            {"error_code": "NO_FEATURES", "error": "No features found in the GML file."},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    geojson_path = os.path.join(upload_dir, f"{file_uuid}.geojson")
                    convert_gml_to_geojson(file_path, geojson_path)
                    file_path = geojson_path
                    original_url = f'/media/uploads/{file_uuid}/{file_uuid}.geojson'
                    file_extension = ".geojson"            

                ## POINT CLOUD 
                elif file_extension.endswith('las') or file_extension.endswith('laz') :
                    print("[INFO] Pointcloud detected !")
                    t = threading.Thread(
                        target=send_to_flyvast,
                        args=[file],
                        daemon=True,
                    )
                    t.start()
                    result = graph_manager.add_pointcloud_to_dataset( dataset_uri,file_path,original_url,file.flyvast_pointcloud["pointcloud_id"],file.flyvast_pointcloud["pointcloud_uuid"])

                elif file_extension.lower() in ('.geojson', '.json'):
                    ## GEOJSON or JSON
                    print(f"[INFO] Starting processing {file_extension} ")

                else:
                    return Response({'error': f'❌ Failed: Unsupported file type {file_extension}. Supported types are .zip (Shapefile), .gml ,.geojson, .json, .las, .laz, .xyz'}, status=status.HTTP_400_BAD_REQUEST)
                
                if file_extension.lower() in ('.geojson', '.json'):
                    remove_html_tags(file_path, keys=())
                    validation = validate_geojson_file(file_path)
                    if not validation['valid']:
                        graph_manager.delete_all(str(dataset_uri))
                        shutil.rmtree(upload_dir, ignore_errors=True)
                        e=validation['message']
                        return Response({'error': f'❌ Failed: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    else:
                        graph_manager.add_geojson_to_dataset(dataset_uri,file_path,original_url)
                    # processor.process(file_path)
                        # process_ontology_file(user_id, file_path)

                # processor.save(ontology_file_path)
            except Exception as e:
                return Response({'error': f'❌ Failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            data = {
                'uuid': file_uuid,
                'owl_path': None,# I removed the ontology, no one downloaded it.
                'map_path': file_path,
                'metadata': metadata
            }
            # Save in Database
            serializer = UploadedFileSerializer(data=data)
            if serializer.is_valid():
                serializer.save()

            return Response({
                'message': 'File uploaded and ontology processed successfully.',
                'uuid': file_uuid,
                'ontology_url': None,# I removed the ontology
                'map_url': original_url
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
def send_to_flyvast(file):
    with open(file.temporary_file_path(), 'rb') as f:
        
        def read_in_chunks(file_object):
            while True:
                data = file_object.read(MAX_CHUNK_SIZE)
                if not data:
                    break
                yield data
        
        index_chunk = 0
        for chunk in read_in_chunks(f):
            chunk_zipped = gzip.compress(chunk)
        
            percentage = min(index_chunk * MAX_CHUNK_SIZE / file.size, 1) * 100
            size = len(chunk_zipped)
            prefix = f"{index_chunk}".zfill(10)
            chunk_name = f"{prefix}-{file.name}"
            upload_url = file.flyvast_pointcloud["upload_url"]
            
            url = f"{upload_url}&name={chunk_name}&bytes={file.size}&percentage={percentage}&size={size}"
            requests.post(url, chunk_zipped)
            
            index_chunk += 1
            
    requests.get(file.flyvast_pointcloud["treatment_url"])