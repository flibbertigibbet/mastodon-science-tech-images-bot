#!/usr/bin/env python3
import json
import os
import random

from mastodon import Mastodon
from PIL import Image
from resizeimage import resizeimage
import requests


API_GOV_KEY = ""  # key to call Smithsonian API. Sign up at: https://api.data.gov/signup/
MASTO_ACCESS_TOKEN = ""
MASTO_BASE_URL = "https://botsin.space"
IMAGE_PATH = "/tmp/smith_image.jpg"
UNIT_CODES_PATH = "unit_codes.json"
BASE_API_URL = (
    "https://api.si.edu/openaccess/api/v1.0/category/science_technology/search"
)
MAX_IMAGE_SIZE = 1048576 * 10
MAX_PIXELS = 1638400
IMAGE_RESIZE = 1280
FREE_LICENSE = "CC0"

unit_codes = {}
with open(UNIT_CODES_PATH, "r") as unit_codes_file:
    unit_codes = json.loads(unit_codes_file.read())


def lambda_handler(event, context):
    return try_random_museums()


def try_random_museums():
    looking = True
    while looking:
        # API docs: https://edan.si.edu/openaccess/apidocs
        query_url = f"{BASE_API_URL}?api_key={API_GOV_KEY}&sort=random&q=online_media_type:Images"
        random_unit_code = random.choice(list(unit_codes.keys()))
        query_url += f"%20AND%20unit_code:{random_unit_code}"
        response = requests.get(query_url)
        if response.ok:
            resp_json = response.json()
            if resp_json.get("status") == 200:
                found_rows = resp_json["response"]["rowCount"]
                if found_rows == 0:
                    print(
                        f"Found no images for random unit code {random_unit_code}; trying again"
                    )
                    continue
                else:
                    looking = False

                return process_response(resp_json, random_unit_code)
            else:
                print(
                    f"Got bad result from API request: {resp_json.get('status')}: {resp_json.get('response').get('message')}"
                )
                return {
                    "statusCode": 500,
                    "body": json.dumps(
                        f"Got bad result from API request: {resp_json.get('status')}: {resp_json.get('response').get('message')}"
                    ),
                }
        else:
            print(f"API request failed: {response.status_code}: {response.reason}")
            return {
                "statusCode": 500,
                "body": json.dumps(
                    f"API request failed: {response.status_code}: {response.reason}"
                ),
            }


def process_response(resp_json, random_unit_code):
    random_images = resp_json["response"]["rows"]
    print(
        f"Successfully got {len(random_images)} random images from API for random unit code {random_unit_code}"
    )
    for result in random_images:
        id = result.get("id")
        title = result.get("title")
        if not title:
            continue  # shouldn't happen

        content = result.get("content")
        access = (
            content.get("descriptiveNonRepeating").get("metadata_usage").get("access")
        )
        if access != FREE_LICENSE:
            continue

        image_found = find_image(id, title, content)
        if image_found:
            return image_found


def find_image(id, title, content):
    desc = content.get("descriptiveNonRepeating")
    media = desc.get("online_media").get("media")
    for medium in media:
        image_url = medium.get("content")
        if image_url:
            image_response = requests.get(image_url)
            if image_response.ok:
                image_saved = upload_image(
                    id, title, content, desc, image_url, image_response
                )
                if image_saved:
                    return image_saved
            else:
                print(
                    f"Failed to download image. {image_response.status_code}: {image_response.reason}"
                )

    print(f"No images found in any of the responses!")
    return None


def upload_image(id, title, content, desc, image_url, image_response):
    try:
        with open(IMAGE_PATH, "wb") as image_file:
            image_file.write(image_response.content)

        with open(IMAGE_PATH, "rb") as image_file:
            with Image.open(image_file) as image:
                if (
                    os.path.getsize(IMAGE_PATH) > MAX_IMAGE_SIZE
                    or (image.width * image.height) > MAX_PIXELS
                ):
                    print("Image is too large; resizing.")
                    image = resizeimage.resize_thumbnail(
                        image, [IMAGE_RESIZE, IMAGE_RESIZE]
                    )
                    image.save(IMAGE_PATH, image.format)
                    print("Successfully resized image")

            print(f"Successfully saved image from {image_url}")
            print(f"Going to post {title} with image from {image_url}")
    except Exception as ex:
        print(f"Failed to save image from {image_url}: {ex}")
        return None

    return post_to_mastodon(id, title, desc, content)


def post_to_mastodon(id, title, desc, content):
    unit_code = desc.get("unit_code")
    link = desc.get("record_link")
    freetext = content.get("freetext")
    place = content.get("place")
    if place and len(place) > 0:
        place = place[0].get("content")
    collection_date = freetext.get("date")
    if collection_date and len(collection_date) > 0:
        collection_date = collection_date[0].get("content")

    museum = unit_codes.get(unit_code, unit_code)
    print(
        f"ID: {id} museum: {museum} place: {place} date: {collection_date} link: {link}"
    )
    try:
        mastodon = Mastodon(
            access_token=MASTO_ACCESS_TOKEN, api_base_url=MASTO_BASE_URL
        )
        print("Connected to Mastodon successfully")
        masto_media = None
        masto_media = mastodon.media_post(
            IMAGE_PATH, description=title, mime_type="image/jpeg"
        )
        media_id = masto_media.get("id")
        if media_id:
            print(f"Media upload requested successfully. Media ID: {media_id}")
            status = f"{title}\n{museum}"
            if place:
                status += f"\n{place}"
            if collection_date:
                status += f"\n{collection_date}"
            if link:
                status += f"\n{link}"
            toot = mastodon.status_post(
                status, media_ids=[media_id], visibility="public", language="en"
            )
            return {
                "statusCode": 200,
                "body": json.dumps(f"Posted successfully! {toot.id} at {toot.url}"),
            }
        else:
            print(f"No ID returned for attempted image upload! {masto_media}")
    except Exception as ex:
        print(f"Failed to post to Mastodon. {ex}")
        return {
            "statusCode": 500,
            "body": json.dumps(f"Failed to post to Mastodon. {ex}"),
        }
