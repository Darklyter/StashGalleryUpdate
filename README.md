# StashGalleryUpdate
 Dumb little script to match and update Stash galleries from scenes

A quick little python script that will attempt to match galleries with the scenes that they go to.

This is based on some assumptions...  1) that the gallery has the same base name as the video file and 2) that the gallery is in a single file (like a zip).

It will first pull a list of all of the galleries in Stash, then step through any that don't already have an associated SceneID.  It will query Stash based on the filename of the gallery zip to find any matching scenes with that same filename.  (Trailing punctuation is removed from the filename, and also if it can't find a match it will try without " - " entries in the filename)

If it finds a match then it will attach the scene id to the gallery and update the gallery metadata from the scene, which includes:
Title
Date
Description
Rating
Studio
Tags
Performers
URL (Of the scene)


This is a pretty dumb script with very little intelligence for matching or protection.  If you have multiple scenes with the same filename for some reason, I'm not sure what it would do (though it should just grab the first one for data).  File path is ignored, and the search is inclusive into the scene filename fut they don't have to be exact.

So a gallery of: "This is the best scene.zip" would match against "MySite - 2022-01-01 - This is the best scene ever! (Mia Malkova, Keisha Grey) [1080p].mp4"

Obviously the more exact the two are to each other the less you have to worry about false hits.  The standard "Studio - Date - Title" name schema should be pretty safe.