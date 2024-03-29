import re
import requests
import pathlib
from string import punctuation

stash_instance = "http://192.168.1.71:9999"

gallery_query = 'query {findGalleries(gallery_filter:{is_missing: "studio_id"}, filter:{per_page: -1}) {galleries{id title scenes{id} files {path basename}}}}'
update_query = "mutation GalleryUpdate($input : GalleryUpdateInput!) {galleryUpdate(input: $input) {id title}}"

scene_query = '''
query {findScenes(scene_filter:{path:{value:"\\"<FILENAME>\\"",modifier:INCLUDES}})
  {
    scenes{
      id
      title
      url
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


def buildInput(scene, galleryid):
    scene = scene['data']['findScenes']['scenes'][0]
    input = {}
    update = {}
    update['id'] = int(galleryid)
    update['url'] = scene['url']
    update['title'] = scene['title']
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
        if not len(gallery['scenes']) and len(gallery['files']):
            result = None
            if len(gallery['files']):
                bare_name = re.search(r'(.*)\.\w{3,4}$', gallery['files'][0]['basename']).group(1)
            else:
                bare_name = pathlib.PurePath(gallery['files'][0]['path'])
                bare_name = bare_name.name

            bare_name = bare_name.strip(punctuation)
            scene = callGraphQL(scene_query.replace("<FILENAME>", bare_name))
            if len(scene['data']['findScenes']['scenes']):
                update_data = buildInput(scene, gallery['id'])
                print(f"Updating Gallery: \"{bare_name}\" with data from scene: \"{scene['data']['findScenes']['scenes'][0]['title']}\"")
                result = callGraphQL(update_query, update_data)
            else:
                # My personal edge case, most files are renamed to remove the original ' - ' between filename elements
                scene = callGraphQL(scene_query.replace("<FILENAME>", bare_name.replace(" - ", " ")))
                if len(scene['data']['findScenes']['scenes']):
                    update_data = buildInput(scene, gallery['id'])
                    print(f"Updating Gallery: \"{bare_name}\" with data from scene: \"{scene['data']['findScenes']['scenes'][0]['title']}\"")
                    # ~ result = callGraphQL(update_query, update_data)
            if not result:
                print(f"Couldn't find a match for gallery: \"{bare_name}\"")
