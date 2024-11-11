#!/usr/bin/env python3
import json
import os
import random

from mastodon import Mastodon
from PIL import Image
from resizeimage import resizeimage
import requests


API_GOV_KEY = ""  # key to call Smithsonian API. Sign up at: https://api.data.gov/signup/
MASTO_ACCESS_TOKEN = "" # access token for your bot (under dev settings)
MASTO_BASE_URL = "https://banderkat.social" # URL to your Mastodon server
IMAGE_PATH = "/tmp/smith_image.jpg"
UNIT_CODES_PATH = "unit_codes.json"
BASE_API_URL = (
    "https://api.si.edu/openaccess/api/v1.0/category/science_technology/search"
)
MAX_IMAGE_SIZE = 1048576 * 10
MAX_PIXELS = 1638400
IMAGE_RESIZE = 1280
FREE_LICENSE = "CC0"
MAX_DESCRIPTION_LEN = 1500 # max size of a status post
MAX_FIELD_LEN = 200 # arbitrary cutoff max length for a line in the post

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
    desc = content.get("descriptiveNonRepeating") if content is not None else None
    online_media = desc.get("online_media") if desc is not None else None
    media = online_media.get("media") if online_media is not None else ""
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


def build_tag_from_freetext(freetext, fieldName):
    free_tag_label = ""
    free_field = freetext.get(fieldName)
    if free_field and len(free_field) > 0:
        for free_tag in free_field:
            free_tag_label += f"\n{free_tag.get('label')}: {free_tag.get('content')}"
    return free_tag_label if len(free_tag_label) < MAX_FIELD_LEN else ""


def post_to_mastodon(id, title, desc, content):
    unit_code = desc.get("unit_code")
    link = desc.get("record_link")
    freetext = content.get("freetext") if content is not None else None
    place = content.get("place")
    if not place:
        place = build_tag_from_freetext(freetext, "place")
    collection_date = build_tag_from_freetext(freetext, "date")
    freetext_name = build_tag_from_freetext(freetext, "name")
    freetext_notes = build_tag_from_freetext(freetext, "notes")
    freetext_physical_description = build_tag_from_freetext(freetext, "physicalDescription")
    freetext_credit_line = build_tag_from_freetext(freetext, "creditLine")
    freetext_data_source = build_tag_from_freetext(freetext, "dataSource")
    freetext_object_type = build_tag_from_freetext(freetext, "objectType")

    freetext_info = ''
    if freetext_name:
        freetext_info += f"\n{freetext_name}"
    if freetext_notes:
        freetext_info += f"\n{freetext_notes}"
    if freetext_physical_description:
        freetext_info += f"\n{freetext_physical_description}"
    if freetext_object_type:
        freetext_info += f"\n{freetext_object_type}"
    if freetext_credit_line:
        freetext_info += f"\n{freetext_credit_line}"
    if freetext_data_source:
        freetext_info += f"\n{freetext_data_source}"

    if len(freetext_info) > (MAX_DESCRIPTION_LEN - MAX_FIELD_LEN):
        freetext_info = ''

    museum = unit_codes.get(unit_code, unit_code)
    print(
        f"ID: {id} museum: {museum} place: {place} date: {collection_date} link: {link} freetext info: {freetext_info}"
    )
    try:
        mastodon = Mastodon(
            access_token=MASTO_ACCESS_TOKEN, api_base_url=MASTO_BASE_URL
        )
        print("Connected to Mastodon successfully")
        masto_media = None
        alt_text = title
        if freetext_name:
            alt_text += f"\n{freetext_name}"
        if freetext_physical_description:
            alt_text += f"\n{freetext_physical_description}"

        masto_media = mastodon.media_post(
            IMAGE_PATH, description=alt_text, mime_type="image/jpeg"
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
            if freetext_info and (len(status + freetext_info) < MAX_DESCRIPTION_LEN):
                status += f"\n{freetext_info}"
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
