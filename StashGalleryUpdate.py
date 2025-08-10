import re
import requests
import pathlib
from string import punctuation

stash_instance = "http://192.168.1.71:9999"

gallery_query = 'query {findGalleries(gallery_filter:{is_missing: "studio_id"}, filter:{per_page: -1, sort: "created_at", direction: DESC}) {galleries{id title scenes{id} files {path basename}}}}'
update_query = "mutation GalleryUpdate($input : GalleryUpdateInput!) {galleryUpdate(input: $input) {id title}}"

scene_query = '''
query {findScenes(scene_filter:{path:{value:"<FILENAME>",modifier:MATCHES_REGEX}})
  {
    scenes{
      id
      title
      url
      code
      date
      details
      rating100
      studio{id name}
      tags{id name}
      performers{id name}
    }
  }
}
'''

noid_scene_query = '''
query {findScenes(scene_filter:{path:{value:"\\"<FILENAME>\\"",modifier:INCLUDES}})
  {
    scenes{
      id
      title
      url
      code
      date
      details
      rating100
      studio{id name}
      tags{id name}
      performers{id name}
    }
  }
}
'''

def callGraphQL(query, variables=None, retry=True):
    graphql_server = stash_instance + "/graphql"

    jsondata = {'query': query}
    if variables is not None:
        jsondata['variables'] = variables
    try:
        response = requests.post(graphql_server, json=jsondata)
        if response.status_code == 200:
            result = response.json()
            if result.get("data", None):
                return result
        else:
            print("GraphQL query failed to run by returning code of {}. Query: {}".format(response.status_code, query))
            raise Exception("GraphQL error")
    except Exception as err:
        print(f"An error occurred: {err}")


def buildInput(scene, galleryid, filepart):
    scene = scene['data']['findScenes']['scenes'][0]
    input = {}
    if scene:
        update = {}
        update['id'] = int(galleryid)
        update['url'] = scene['url']
        update['title'] = scene['title'] + filepart
        update['date'] = scene['date']
        update['details'] = scene['details']
        if scene['rating100']:
            update['rating100'] = scene['rating100']
        update['scene_ids'] = [int(scene['id'])]
        if "id" in scene['studio']:
            update['studio_id'] = int(scene['studio']['id'])
        if "tags" in scene and len(scene['tags']):
            update['tag_ids'] = []
            for tag in scene['tags']:
                update['tag_ids'].append(int(tag['id']))
        if "performers" in scene and len(scene['performers']):
            update['performer_ids'] = []
            for performer in scene['performers']:
                update['performer_ids'].append(int(performer['id']))
        input['input'] = update
    return input


if __name__ == "__main__":
    galleries = callGraphQL(gallery_query)
    for gallery in galleries['data']['findGalleries']['galleries']:
        if gallery['files'] and "/Wow Girls/" not in gallery['files'][0]['path'] and "/MetArtNetwork/" not in gallery['files'][0]['path'] \
            and "/VNANetwork/" not in gallery['files'][0]['path'] and "/TheFemaleOrgasm/" not in gallery['files'][0]['path'] \
            and "/Cosmid/" not in gallery['files'][0]['path']:
            if not len(gallery['scenes']) and len(gallery['files']):
                result = None
                if len(gallery['files']):
                    bare_name = re.search(r'(.*)\.\w{3,4}$', gallery['files'][0]['basename']).group(1)
                else:
                    bare_name = pathlib.PurePath(gallery['files'][0]['path'])
                    bare_name = bare_name.name
                custom_punctuation = punctuation.replace("[", "").replace("]", "")
                bare_name = bare_name.strip(custom_punctuation)
                if re.search(r"-(File\d+)$", bare_name):
                    filepart = re.search(r"-(File\d+)$", bare_name).group(1)
                    bare_name = bare_name.replace(f"-{filepart}", "")
                    partnum = re.search(r'(\d+)', filepart)
                    if partnum:
                        partnum = int(partnum.group(1))
                        if partnum > 1:
                            filepart = " (" + filepart.replace("File", "Gallery ") + ")"
                        else:
                            filepart = ""
                else:
                    filepart = ""

                bare_name = re.sub(r'\[\d+x\d+\]', "", bare_name).strip()
                performers = re.search(r'.*( \(.*?\) )', bare_name)
                if performers:
                    bare_name = bare_name.replace(performers.group(1), '').strip()
                sceneid = re.search(r'.*(\[.*?\])', bare_name)
                if sceneid:
                    sceneid = sceneid.group(1)
                    sceneid_query = sceneid.replace("[", "\\\\[").replace("]", "\\\\]")
                    bare_name = bare_name.replace(sceneid, ".*" + sceneid_query).strip()
                    scene_query_text = (scene_query.replace("<FILENAME>", bare_name))
                else:
                    scene_query_text = (noid_scene_query.replace("<FILENAME>", bare_name))

                scene = callGraphQL(scene_query_text)
                # ~ print(scene_query_text, scene)
                if len(scene['data']['findScenes']['scenes']):

                    update_data = buildInput(scene, gallery['id'], filepart)
                    if update_data:
                        print(f"Updating Gallery: \"{bare_name + filepart}\" with data from scene: \"{scene['data']['findScenes']['scenes'][0]['title']}\" (Studio Code: {scene['data']['findScenes']['scenes'][0]['code']})")
                        result = callGraphQL(update_query, update_data)
                    else:
                        print(f"Couldn't find valid data for video file to updating gallery: \"{bare_name}\"")
                else:
                    # My personal edge case, most files are renamed to remove the original ' - ' between filename elements
                    scene = callGraphQL(scene_query.replace("<FILENAME>", bare_name.replace(" - ", " ")))
                    if len(scene['data']['findScenes']['scenes']):
                        update_data = buildInput(scene, gallery['id'])
                        print(f"Updating Gallery: \"{bare_name}\" with data from scene: \"{scene['data']['findScenes']['scenes'][0]['title']}\"")
                        # ~ result = callGraphQL(update_query, update_data)
                if not result:
                    print(f"Couldn't update gallery: \"{bare_name}\"")
