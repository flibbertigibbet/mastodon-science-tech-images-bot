# Mastodon bot 🤖

[@sciencetechimages@botsin.space](https://botsin.space/@sciencetechimages)

Mastodon bot to post random science and tech museum images from the Smithsonian API.

(Not affiliated with the Smithsonian.)

## Requirements

 This Python script uses the packages:
  - [Mastodon.py](https://mastodonpy.readthedocs.io/en/stable/index.html)
  - [requests](https://requests.readthedocs.io/en/latest/)
  - [python-resize-image](https://github.com/VingtCinq/python-resize-image)

Edit `lambda_function.py` to set the Smithsonian API key (sign up [here](https://api.data.gov/signup/)) and the Mastodon access token for your bot account (viewable under settings once the account has been marked as a bot account).


## Deploying on AWS

Package the dependencies, script, and JSON file of museum codes:
```
python3.9 -m venv venv
source venv/bin/activate
pip install --target ./package Mastodon.py requests python-resize-image
cd package && rm -r PIL && rm -r Pillow*
zip -r ../bot.zip .
cd ..
zip bot.zip lambda_function.py
zip bot.zip unit_codes.json
```

The Pillow and PIL diretories are deleted from the package above as they are not compatible with the Lambda environment. Instead, the Pillow library can be added as a layer by ARN `arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p39-pillow:1`, found in [Keith's layers](https://github.com/keithrozario/Klayers/).

Upload the `bot.zip` file created above to a new Lambda function and add the Pillow layer.

To schedule the bot posts, create a fixed-rate schedule using [EventBridge scheduler](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-run-lambda-schedule.html).
