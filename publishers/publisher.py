import discord
import requests
from requests_oauthlib import OAuth1
from utils import Keys

# Social media posting functions
def post_to_twitter(content):
    url = "https://api.twitter.com/2/tweets"
    auth = OAuth1(Keys.API_Key, Keys.API_Key_Secret, Keys.Access_Token, Keys.Access_Token_Secret)
    payload = {"text": content}
    response = requests.post(url, auth=auth, json=payload)
    if response.status_code == 201:
        tweet_id = response.json().get("data", {}).get("id")
        print(f"Posted tweet: {content}")
        return tweet_id
    else:
        print(f"Failed to post to Twitter: {response.text}")
        return None

def post_to_linkedin(content):
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {Keys.Linkedin_Access_Token}",
        "Content-Type": "application/json"
    }
    payload = {
        "author": Keys.LINKEDIN_AUTHOR_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": content},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 201:
        print("Posted to LinkedIn successfully!")
    else:
        print(f"Failed to post to LinkedIn: {response.text}")

# Discord Client that listens on specific channels and reposts messages
ADDITIONAL_CHANNEL_IDS = [1323659231064490044, 1341449447653118059]
TARGET_CHANNEL_ID = 855359994547011604
NOTEBOOK_CHANNEL_ID = Keys.NOTEBOOK_CHANNEL_ID

class DiscordClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"Logged in as {self.user}")

    async def on_message(self, message):
        if message.channel.id in [int(NOTEBOOK_CHANNEL_ID)] + ADDITIONAL_CHANNEL_IDS:
            content = message.content
            print(f"New message in channel {message.channel.id}: {content}")
            target_channel = self.get_channel(TARGET_CHANNEL_ID)
            if target_channel:
                await target_channel.send(content)
            # Post to social platforms if the message comes from specific channels
            if message.channel.id == int(NOTEBOOK_CHANNEL_ID) or message.channel.id == ADDITIONAL_CHANNEL_IDS[1]:
                post_to_linkedin(content)
                post_to_twitter(content)

def main():
    client = DiscordClient()
    client.run(Keys.DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    main()
