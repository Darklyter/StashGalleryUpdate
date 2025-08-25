import re
import requests
import logging
import argparse
import json
import os
from string import punctuation
from datetime import datetime, timedelta
from math import ceil

# Configure logging level
logging.basicConfig(level=logging.INFO)

# Stash GraphQL endpoint
stash_instance = "http://192.168.1.71:9999"

# Scene index cache settings
cache_file = "scene_cache.json"
cache_max_age = timedelta(days=1)
per_page = 50000  # Number of scenes per page when querying

# Paths to exclude from processing
excluded_paths = [
    "/Wow Girls/", "/MetArtNetwork/", "/VNANetwork/",
    "/TheFemaleOrgasm/", "/Cosmid/"
]

# GraphQL queries
gallery_query = '''
query {
  findGalleries(gallery_filter:{is_missing: "studio_id"}, filter:{per_page: -1, sort: "created_at", direction: DESC}) {
    galleries {
      id title scenes{id} files {path basename}
    }
  }
}
'''

scene_count_query = '''
query {
  findScenes(scene_filter:{}) {
    count
  }
}
'''

scene_detail_query = '''
query SceneByID($id: ID!) {
  findScene(id: $id) {
    id title url code date details rating100
    studio { id name }
    tags { id name }
    performers { id name }
  }
}
'''

scene_quick_query = '''
query SceneByID($id: ID!) {
  findScene(id: $id) {
    id title date
    studio { name }
  }
}
'''

update_query = '''
mutation GalleryUpdate($input : GalleryUpdateInput!) {
  galleryUpdate(input: $input) {id title}
}
'''

# Helper: Send GraphQL query to Stash
def callGraphQL(query, variables=None):
    try:
        response = requests.post(f"{stash_instance}/graphql", json={'query': query, 'variables': variables})
        response.raise_for_status()
        result = response.json()
        return result if result.get("data") else None
    except Exception as err:
        logging.error(f"GraphQL error: {err}")
        return None

# Helper: Build mutation input from scene data
def buildInput(scene, galleryid, filepart):
    try:
        update = {
            'id': int(galleryid),
            'url': scene.get('url'),
            'title': scene.get('title', '') + filepart,
            'date': scene.get('date'),
            'details': scene.get('details'),
            'scene_ids': [int(scene['id'])],
        }

        if scene.get('rating100'):
            update['rating100'] = scene['rating100']
        if scene.get('studio', {}).get('id'):
            update['studio_id'] = int(scene['studio']['id'])
        if scene.get('tags'):
            update['tag_ids'] = [int(tag['id']) for tag in scene['tags']]
        if scene.get('performers'):
            update['performer_ids'] = [int(p['id']) for p in scene['performers']]

        return {'input': update}
    except Exception as e:
        logging.warning(f"Failed to build input: {e}")
        return None

# Helper: Normalize filename for matching
def normalize_filename(basename):
    name = re.sub(r'\.\w{3,4}$', '', basename)
    name = name.strip(punctuation.replace("[", "").replace("]", ""))
    name = re.sub(r'\[\d+x\d+\]', "", name).strip()
    name = re.sub(r'\s*\(.*?\)', "", name).strip()
    return name

# Helper: Generate fallback candidates for matching
def apply_fallbacks(name):
    candidates = [name]
    candidates.append(name.replace(" - ", " "))
    candidates.append(re.sub(r"\s*?[sS]\d+\s*?[eE]\d+", "", candidates[-1]).strip())
    candidates.append(re.sub(r"\[.*?\]", "", candidates[-1]).strip())
    return candidates

# Helper: Match scene ID from candidate strings
def match_scene_id(candidates, scene_index, verbose=False):
    for level, candidate in enumerate(candidates):
        if verbose:
            logging.info(f"🔍 Searching with candidate (Level {level}): \"{candidate}\"")
        pattern = re.compile(rf"(?i){re.escape(candidate)}")
        for scene_path in scene_index:
            if pattern.search(scene_path):
                if verbose:
                    logging.info(f"✅ Match found in scene path: \"{scene_path}\"")
                return scene_index[scene_path], level
    return None, None

# Helper: Load scene index from cache or Stash
def load_scene_index(force=False):
    if not force and os.path.exists(cache_file):
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        if datetime.now() - mtime < cache_max_age:
            logging.info("🟣 Using cached scene index...")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

    logging.info("🟣 Fetching total scene count...")
    count_result = callGraphQL(scene_count_query)
    if not count_result or 'data' not in count_result or 'findScenes' not in count_result['data']:
        logging.error("❌ Failed to retrieve scene count.")
        return {}

    total_scenes = count_result['data']['findScenes']['count']
    total_pages = ceil(total_scenes / per_page)
    logging.info(f"🟣 Total scenes: {total_scenes}, Pages to fetch: {total_pages}")

    scene_index = {}
    page = 1
    total_loaded = 0

    while page <= total_pages:
        logging.info(f"🟣 Fetching scene page {page} of {total_pages}...")
        paged_query = f'''
        query {{
          findScenes(scene_filter: {{}}, filter: {{page: {page}, per_page: {per_page}}}) {{
            scenes {{
              id
              files {{ path }}
            }}
          }}
        }}
        '''
        result = callGraphQL(paged_query)
        if not result or 'data' not in result or 'findScenes' not in result['data']:
            logging.error(f"❌ Failed to load scenes on page {page}")
            break

        scenes = result['data']['findScenes']['scenes']
        if not scenes:
            break

        for scene in scenes:
            for file in scene.get('files', []):
                path = file.get('path')
                if path:
                    scene_index[path.strip().lower()] = scene['id']

        total_loaded += len(scenes)
        page += 1

    logging.info(f"🟣 Completed loading {total_loaded} scenes into index.")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(scene_index, f)

    return scene_index

# Helper: Timestamp for logging
def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Update Stash galleries with scene metadata.")
    parser.add_argument('--dry-run', action='store_true', help="Simulate updates without sending mutations")
    parser.add_argument('--force', action='store_true', help="Force fresh scene query and ignore cache")
    parser.add_argument('--verbose', action='store_true', help="Show detailed matching steps")
    parser.add_argument('--allow-fallback', action='store_true', help="Enable fallback matching strategies")
    parser.add_argument('--start-at', type=int, default=1, help="Start processing at this gallery index (1-based)")
    parser.add_argument('--limit', type=int, help="Limit number of galleries to process")
    args = parser.parse_args()

    # Load galleries from Stash
    logging.info("🟡 Loading galleries from Stash...")
    galleries = callGraphQL(gallery_query)
    if not galleries:
        logging.error("❌ Failed to retrieve galleries.")
        exit()

    all_galleries = galleries['data']['findGalleries']['galleries']
    total_galleries = len(all_galleries)
    logging.info(f"🟣 Total galleries available: {total_galleries}")

    # Apply --start-at and --limit filters
    start_index = args.start_at - 1
    end_index = start_index + args.limit if args.limit else total_galleries
    selected_galleries = all_galleries[start_index:end_index]
    logging.info(f"🟣 Galleries to process: {len(selected_galleries)} (from index {args.start_at} to {end_index})")

    # Load or refresh scene index
    scene_index = load_scene_index(force=args.force)

    # Initialize counters and unmatched list
    matched = 0
    failed = 0
    skipped = 0
    unmatched = []

    # Process each gallery
    for index, gallery in enumerate(selected_galleries, start=args.start_at):
        file_info = gallery.get('files', [{}])[0]
        path = file_info.get('path', '')
        basename = file_info.get('basename', '')

        # Skip excluded paths
        if any(excl in path for excl in excluded_paths):
            skipped += 1
            continue

        # Skip galleries that already have scenes or lack a basename
        if gallery['scenes'] or not basename:
            skipped += 1
            continue

        # Normalize filename and extract filepart suffix
        normalized = normalize_filename(basename)
        filepart = ""
        match = re.search(r"-(File\d+)$", normalized)
        if match:
            filepart = match.group(1)
            normalized = normalized.replace(f"-{filepart}", "")
            partnum = int(re.search(r'\d+', filepart).group())
            filepart = f" (Gallery {partnum})" if partnum > 1 else ""

        # Verbose logging for matching start
        if args.verbose:
            logging.info(f"{timestamp()} 🔍 [{index}/{end_index}] Starting match for: \"{normalized}\"")

        # Generate candidate strings for matching
        candidates = apply_fallbacks(normalized) if args.allow_fallback else [normalized]
        matched_id = None
        fallback_level = None

        # Attempt to match scene ID from candidates
        for level, candidate in enumerate(candidates):
            if args.verbose:
                logging.info(f"{timestamp()} 🔍 Trying candidate (Level {level}): \"{candidate}\"")
            pattern = re.compile(rf"(?i){re.escape(candidate)}")
            for scene_path in scene_index:
                if pattern.search(scene_path):
                    matched_id = scene_index[scene_path]
                    fallback_level = level
                    if args.verbose:
                        logging.info(f"{timestamp()} ✅ Match found in scene path: \"{scene_path}\"")
                    break
            if matched_id:
                break

        # If match found, fetch scene data and update gallery
        if matched_id:
            query_to_use = scene_quick_query if args.dry_run else scene_detail_query
            scene_data = callGraphQL(query_to_use, {"id": matched_id})
            if scene_data and scene_data['data']['findScene']:
                scene = scene_data['data']['findScene']
                update_data = buildInput(scene, gallery['id'], filepart)
                fallback_note = f" (Fallback Level: {fallback_level})" if fallback_level else ""
                logging.info(f"{timestamp()} 🟢 [{index}/{end_index}] Matched \"{normalized}\" → \"{scene['title']}\"{fallback_note}")
                if args.dry_run:
                    studio_name = scene.get('studio', {}).get('name', 'None')
                    logging.info(
                        f"{timestamp()} 🧪 Dry-run: ID={scene['id']} | Studio=\"{studio_name}\" | Date={scene.get('date', 'None')} | "
                        f"Title=\"{scene['title']}\"\n"
                    )
                else:
                    callGraphQL(update_query, update_data)
                matched += 1
            else:
                logging.warning(f"{timestamp()} 🔴 [{index}/{end_index}] Failed to fetch scene data for ID: {matched_id}")
                failed += 1
        else:
            logging.warning(f"{timestamp()} 🔴 [{index}/{end_index}] No match for Gallery: \"{normalized}\"")
            unmatched.append(normalized)
            failed += 1

    # Write unmatched gallery names to file
    if unmatched:
        with open("unmatched_galleries.txt", "w", encoding="utf-8") as f:
            for name in unmatched:
                f.write(name + "\n")
        logging.info(f"{timestamp()} 📄 Unmatched gallery names written to unmatched_galleries.txt")

    # Final summary
    logging.info(f"{timestamp()} 📊 Summary: {matched} matched, {failed} failed, {skipped} skipped.")
