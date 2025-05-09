import praw
from dotenv import load_dotenv
import os
import google.generativeai as genai
import time
import random
import prawcore
import requests
from bs4 import BeautifulSoup
import base64
import re
from PIL import Image

load_dotenv()

NEON_GREEN = '\033[92m'
CYAN = '\033[96m'
YELLOW = '\033[93m'
RESET_COLOR = '\033[0m'

# Define the brain files directory
BRAIN_FILES_DIR = "bot_brain_files"
REPLIED_POSTS_FILE = os.path.join(BRAIN_FILES_DIR, "replied_posts.txt")
IMG_DIR = "img"

def open_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as infile:
        return infile.read()

# Reddit API credentials
client_id = os.getenv("REDDIT_CLIENT_ID")
client_secret = os.getenv("REDDIT_CLIENT_SECRET")
user_agent = os.getenv("REDDIT_USER_AGENT")
reddit_username = os.getenv("REDDIT_USERNAME")
reddit_password = os.getenv("REDDIT_PASSWORD")

# Google Gemini API credentials
google_api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=google_api_key)

# Create Reddit client
reddit = praw.Reddit(
    client_id=client_id,
    client_secret=client_secret,
    user_agent=user_agent,
    username=reddit_username,
    password=reddit_password
)

# Initialize Gemini Models
comment_generation_model = genai.GenerativeModel('gemini-2.5-pro-exp-03-25')
image_description_model = genai.GenerativeModel('gemini-2.5-pro-exp-03-25')

# Set the subreddits and keywords to search for
subreddits = ["YOUR REDDIT SUBS"]
keywords = ["keyword1, keyword2, etc," ]

def generate_comment(post_title, post_content, url_content, image_description):
    system_message = open_file(os.path.join(BRAIN_FILES_DIR, "persona_and_instructions.txt"))
    in_context_traning = open_file(os.path.join(BRAIN_FILES_DIR, "good_comment_examples.txt"))
    knowledge_base = open_file(os.path.join(BRAIN_FILES_DIR, "knowledge_snippets.txt"))
    important_rules = open_file(os.path.join(BRAIN_FILES_DIR, "output_rules.txt"))
    bad_examples = open_file(os.path.join(BRAIN_FILES_DIR, "avoid_these_comments.txt"))
    
    if image_description:
        url_content = ""  # Exclude url_content if the post contains an image
    
    full_prompt = f"""{system_message}

    CONTEXT:
    [EXAMPLE_COMMENTS]
    {in_context_traning}
    [KNOWLEDGE_BASE]
    {knowledge_base}
    [IMPORTANT_RULES_TO_FOLLOW]
    {important_rules}
    [BAD_EXAMPLE_COMMENTS]
    {bad_examples}
    TASK:
    Post Title: {post_title}
    Post Content: {post_content}, {url_content}, {image_description}
    INSTRUCTIONS:
    Learn from the [CONTEXT] above and write a comment in ONLY lower case letters to the Reddit post from the [TASK] in the same length and style as the [EXAMPLE_COMMENTS] provided by allaboutai-kris.
    Provide a brief, answer without restating the question too much, and limit your response to 3-6 sentences.
    Strictly adhere to the [IMPORTANT_RULES_TO_FOLLOW] and keep the response length similar to the example comments.Carefully review the [BAD_EXAMPLE_COMMENTS] and ensure your generated comment does not exhibit any of the undesirable traits or patterns present in those examples.
    Aim to produce a high-quality, engaging comment that provides value to the discussion while steering clear of the pitfalls illustrated in the bad examples.
    """
    
    generation_config = genai.types.GenerationConfig(
        temperature=0.4,
        max_output_tokens=300
    )
    
    try:
        response = comment_generation_model.generate_content(
            contents=full_prompt,
            generation_config=generation_config
        )
        if response and response.text:
            return response.text.strip()
        else:
            print("Gemini API call for comment generation returned no content or failed.")
            return ""
    except Exception as e:
        print(f"Error calling Gemini API for comment generation: {e}")
        return ""

def scrape_url_content(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        content = soup.get_text()
        content = content.strip()
        content = ' '.join(content.split())
        return content
    except requests.exceptions.RequestException as e:
        print(f"Error scraping URL: {url} - {str(e)}")
        return ""

def download_image(url, post_id):
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        if not os.path.exists(IMG_DIR):
            os.makedirs(IMG_DIR)
        
        file_extension = os.path.splitext(url)[1]
        if not file_extension and any(img_type in url.lower() for img_type in ['.jpg', '.jpeg', '.png']):
             file_extension = ".jpg"
        elif not file_extension:
            file_extension = ".tmp"

        safe_post_id = "".join(c if c.isalnum() else "_" for c in post_id)
        file_name = f"{safe_post_id}{file_extension}"
        file_path = os.path.join(IMG_DIR, file_name)
        
        with open(file_path, "wb") as file:
            file.write(response.content)
        
        return file_path
    except requests.exceptions.RequestException as e:
        print(f"Error downloading image: {url} - {str(e)}")
        return None

def resize_image(image_path, max_size=1024):
    try:
        with Image.open(image_path) as image:
            image.thumbnail((max_size, max_size))
            resized_path = os.path.splitext(image_path)[0] + "_resized.jpg"
            image.save(resized_path, "JPEG")
            return resized_path
    except Exception as e:
        print(f"Error resizing image: {image_path} - {str(e)}")
        return None

def describe_image(image_path):
    try:
        img = Image.open(image_path)
        if img.mode != 'RGB' and image_path.lower().endswith(('.jpg', '.jpeg')):
            img = img.convert('RGB')
            
        text_prompt = "Describe this image and rewrite ALL the text in the image:"
        
        generation_config = genai.types.GenerationConfig(
             max_output_tokens=150 
        )

        response = image_description_model.generate_content(
            contents=[text_prompt, img],
            generation_config=generation_config
        )
        
        if response and response.text:
            return response.text.strip()
        else:
            print("Gemini API call for image description returned no content or failed.")
            return ""
    except FileNotFoundError:
        print(f"Error describing image: File not found at {image_path}")
        return ""
    except Exception as e:
        print(f"Error calling Gemini API for image description or processing image: {e}")
        return ""

def load_replied_posts():
    if os.path.exists(REPLIED_POSTS_FILE):
        with open(REPLIED_POSTS_FILE, "r") as file:
            return set(file.read().splitlines())
    else:
        return set()

def save_replied_posts(replied_posts):
    # Ensure the directory for replied_posts.txt exists
    if not os.path.exists(BRAIN_FILES_DIR):
        os.makedirs(BRAIN_FILES_DIR)
    with open(REPLIED_POSTS_FILE, "w") as file:
        file.write("\n".join(replied_posts))

def main():
    last_comment_time = 0
    replied_posts = load_replied_posts()  # Load the IDs of replied posts from the file
    while True:
        for subreddit_name in subreddits:
            print(f"Searching in subreddit: {subreddit_name}")  # Print the subreddit name
            subreddit = reddit.subreddit(subreddit_name)
            try:
                for post in subreddit.new(limit=50):  # Adjust the limit as needed
                    if post.id in replied_posts:
                        continue  # Skip the post if already replied to
                    post_title = post.title.lower()
                    
                    for keyword in keywords:
                        if keyword.lower() in post_title:
                            current_time = time.time()
                            elapsed_time = current_time - last_comment_time
                            if elapsed_time >= random.randint(3600, 7200):  # Random wait time between 60 and 120 minutes
                                post_content = post.selftext.lower()
                                url_content = ""
                                image_description = ""
                                
                                urls = re.findall(r'(https?://\S+)', post_content)
                                if urls:
                                    url = urls[0]  # Take the first URL found in the post content
                                    url_content = scrape_url_content(url)
                                
                                if post.url and re.search(r"\.(jpg|jpeg|png|gif|bmp)$", post.url, re.IGNORECASE):
                                    image_path = download_image(post.url, post.id)
                                    if image_path:
                                        resized_path = resize_image(image_path)
                                        if resized_path:
                                            image_description = describe_image(resized_path)
                                
                                comment_text = generate_comment(post.title, post_content, url_content, image_description)
                                post.reply(comment_text)
                                print(f"Commented on post: {post.title}")
                                print(NEON_GREEN + comment_text + RESET_COLOR)
                                print("---")
                                last_comment_time = current_time
                                replied_posts.add(post.id)  # Add the post ID to the set of replied posts
                                save_replied_posts(replied_posts)  # Save the updated set of replied posts to the file
                            else:
                                remaining_time = random.randint(3600, 7200) - elapsed_time
                                print(f"Waiting for {remaining_time // 60} minutes and {remaining_time % 60} seconds before commenting again...")
                            break
            except prawcore.exceptions.BadRequest as e:
                print(f"Error: {str(e)}")
                continue
        time.sleep(60)  # Wait for 1 minute before searching again

if __name__ == "__main__":
    main()
