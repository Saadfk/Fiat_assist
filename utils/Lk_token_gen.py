import requests
#ACQUIRES LINKEDIN ACCES TOKEN

# LinkedIn API credentials
CLIENT_ID = "78t4wm588pid93"
CLIENT_SECRET = "UGZGznBUmcDqUHfv"
REDIRECT_URI = "http://localhost:8000"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

# Scopes for personal profile access
SCOPES = ["w_member_social", "profile", "email", "openid"]

# Step 1: Generate the Authorization URL
def get_authorization_url():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
    }
    auth_url = f"https://www.linkedin.com/oauth/v2/authorization"
    return f"{auth_url}?{requests.compat.urlencode(params)}"

# Step 2: Exchange Authorization Code for Access Token
def get_access_token(auth_code):
    payload = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    response = requests.post(TOKEN_URL, data=payload)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        raise Exception(f"Failed to get access token: {response.json()}")

if __name__ == "__main__":
    # Display authorization URL
    print("Go to the following URL to authorize the application:")
    print(get_authorization_url())

    # Prompt for authorization code
    auth_code = input("Paste the authorization code here: ").strip()

    # Exchange code for access token
    try:
        access_token = get_access_token(auth_code)
        print(f"Access Token: {access_token}")
    except Exception as e:
        print(e)
