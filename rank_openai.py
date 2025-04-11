import openai
import pandas as pd
import time
import math
from typing import List, Optional, Dict
from dataclasses import dataclass
import re
import os
from dotenv import load_dotenv
from openai import OpenAI
from config import check_environment_variables

# Load environment variables
load_dotenv()

# Check environment variables
check_environment_variables()

# Initialize OpenAI client with API key from environment
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'),
    base_url="https://api.openai.com/v1")

# API Configuration
MODEL_NAME = "gpt-4o-mini"
DEFAULT_BATCH_SIZE = 10
RATE_LIMIT_DELAY = 1.2  # seconds

# Prompt Configuration
PROMPT_TEMPLATE = PROMPT_TEMPLATE = """
You are curating news for the founder of a €200M AI Gaming fund to help him build thought leadership on LinkedIn.

You will receive article summaries and must assign a **relevance score from 1 to 10**, using the following framework:

---

🎯 Prioritization Criteria

1. **AI is mandatory to score well.**
   - Articles unrelated to AI should get low scores (1–3), even if they talk about gaming or crypto.

2. **AI + Gaming = highest priority.**
   - Prioritize articles where AI is applied to game design, prototyping, monetization, player behavior, studio tools, etc.

3. **AI Agents = strong bonus.**
   - Articles about **AI agents**, agent frameworks, or agent interoperability (even outside gaming) should score **high (8–10)** if they are **strategic or technical in depth**.
   - Business applications or general commentary on agents = **6–7**.

4. **Crypto + AI = moderate.**
   - AI applied to crypto (e.g. trading agents, decentralized agent platforms) should score **no higher than 7–8**, unless there is a clear gaming or agentic innovation.

5. **Product/tech announcements = evaluate for depth.**
   - If it's mostly **marketing** (e.g. chipset release, performance claims, vague AI enablement) → score low (4–6).
   - If the announcement includes **real architectural insights, code, demo, or benchmark** → can score higher (7–9).

6. **Don’t miss foundational breakthroughs.**
   - Some technical or open protocol announcements (e.g. Google’s Agent2Agent) may deserve a **10** even if they are outside gaming — if they reshape the AI or agentic landscape.

---

🧠 Scoring Scale:

- **10** = AI + Gaming + strong insight OR foundational agentic breakthrough
- **8–9** = AI + Gaming (even if not deep) OR strong agent or use-case news
- **6–7** = Agent-related business content, insightful AI outside gaming, or crypto/infra AI with some relevance
- **4–5** = Generic AI product news, performance claims, buzz with little depth
- **1–3** = Not AI-related or pure marketing without relevance

---

💬 Format:
Article 1: 7  
Article 2: 3  
...

Use this lens: *Would this help the fund founder sound like a forward-thinking expert in AI Gaming and agent-based technology on LinkedIn?*
"""


LINKEDIN_PROMPT_TEMPLATE = """You are the Head of Content for WarpzoneAI, a €200M investment fund dedicated to mobile gaming with a focus on AI integration. Create an engaging LinkedIn post about the following article that positions WarpzoneAI as a thought leader and sparks engagement from founders, developers, and industry peers.

Article Title: {title}
Article Summary: {summary}
Keywords: {keywords}

Guidelines for the post:
1. Start with a strong hook that grabs attention within the first 3 lines
2. Highlight the strategic implications for the gaming industry
3. Add a unique point of view or bold insight that goes beyond the article
4. Keep the tone professional but conversational, as if written by a founder or investor
5. Include relevant hashtags (3–5)
6. Add 3–5 well-placed emojis to break the text and add personality
7. End with a thought-provoking question or clear call to action
8. Keep it within 1300 characters (LinkedIn's limit)
9. Include the article URL at the end

Article URL: {url}

Write the post in a format ready to be copied and pasted to LinkedIn:"""

class OpenAIError(Exception):
    """Custom exception for OpenAI API errors."""
    pass

@dataclass
class ArticleBatch:
    """Data class to handle article batches."""
    summaries: List[str]
    start_index: int
    end_index: int
    batch_number: int
    total_batches: int
    prompt: str

def format_prompt(df_batch: pd.DataFrame) -> str:
    """
    Format the prompt for OpenAI API with article summaries.
    
    Args:
        df_batch (pd.DataFrame): Batch of articles to process
        
    Returns:
        str: Formatted prompt with article summaries
    """
    prompt = PROMPT_TEMPLATE

    for i, row in enumerate(df_batch.itertuples(), 1):
        text = row.Summary.strip() if isinstance(row.Summary, str) and row.Summary.strip() else row.Title.strip()
        prompt += f"\n---\nArticle {i}:\n{text}\n"

    return prompt

def process_batch(batch: ArticleBatch) -> List[Optional[int]]:
    """
    Process a batch of articles through the OpenAI API.
    
    Args:
        batch (ArticleBatch): Batch of articles to process
        
    Returns:
        List[Optional[int]]: List of scores for the batch
        
    Raises:
        OpenAIError: If the API request fails
    """
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": batch.prompt}],
            temperature=0,
            max_tokens=500
        )
        
        scores = [None] * len(batch.summaries)
        reply = response.choices[0].message.content

        for line in reply.strip().split('\n'):
            if ':' in line:
                try:
                    idx, score = line.split(':')
                    idx = int(idx.strip().replace("Article", "")) - 1
                    # Try to extract the first number from the score part
                    numbers = re.findall(r'\d+', score.strip())
                    if numbers:
                        score = int(numbers[0])
                        if 1 <= score <= 10:  # Only accept valid scores
                            scores[idx] = score
                except (ValueError, IndexError):
                    continue

        return scores

    except Exception as e:
        raise OpenAIError(f"Failed to process batch {batch.batch_number}: {str(e)}")

def generate_bullet_points_summary(title: str, content: str) -> str:
    """
    Generate a bullet points summary of the article in the specified format.
    
    Args:
        title (str): The article title
        content (str): The article content
        
    Returns:
        str: Formatted bullet points summary
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """You are an expert at analyzing gaming and AI news articles.
                Create a detailed bullet points summary of the article following this exact format:
                
                Key News Item: [Title] (Link)
                ● [Main point 1]
                ● [Main point 2]
                ● [Main point 3]
                ● [Main point 4]
                ● [Main point 5]
                ● <strong>Why does this matter to AI x Gaming:</strong> [Explanation of the article's significance to AI in gaming]
                
                Make sure to:
                1. Extract the most important points from the article
                2. Focus on facts, numbers, and specific details
                3. End with a clear explanation of why this matters to AI in gaming
                4. Keep each bullet point concise but informative
                5. Use the exact format shown above"""},
                {"role": "user", "content": f"Title: {title}\n\nContent: {content}"}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"Error generating bullet points summary: {str(e)}")
        return "Error generating summary"

def batch_gpt_scoring(df: pd.DataFrame, column: str, batch_size: int = 15) -> pd.DataFrame:
    """
    Process a batch of articles with GPT scoring.
    
    Args:
        df (pd.DataFrame): DataFrame containing articles
        column (str): Name of the column containing article content
        batch_size (int): Number of articles to process in each batch
        
    Returns:
        pd.DataFrame: DataFrame with added GPT scores
    """
    try:
        # Calculate number of batches
        n_batches = math.ceil(len(df) / batch_size)
        scores = [None] * len(df)
        
        # Score all articles in batches
        print("🤖 Starting article scoring...")
        for b in range(n_batches):
            start_idx = b * batch_size
            end_idx = min((b + 1) * batch_size, len(df))
            df_batch = df.iloc[start_idx:end_idx]
            
            # Create batch for scoring
            article_batch = ArticleBatch(
                summaries=df_batch[column].tolist(),
                start_index=start_idx,
                end_index=end_idx,
                batch_number=b + 1,
                total_batches=n_batches,
                prompt=format_prompt(df_batch)
            )
            
            print(f"🔍 Processing batch {b + 1}/{n_batches}")
            
            # Get GPT scoring for the batch
            batch_scores = process_batch(article_batch)
            
            # Update scores in the list
            for idx, score in enumerate(batch_scores):
                if score is not None:
                    scores[start_idx + idx] = score
            
            # Add a small delay between batches to respect rate limits
            if b < n_batches - 1:
                time.sleep(RATE_LIMIT_DELAY)
        
        # Update DataFrame with all scores
        df['GPT_Pertinence'] = scores
        df = df.sort_values('GPT_Pertinence', ascending=False)
        #df['Summary'] = df[column].apply(lambda x: x[:300] + '...' if isinstance(x, str) else '')
        
        return df
        
    except Exception as e:
        print(f"❌ Error in batch_gpt_scoring: {str(e)}")
        return df

def generate_bullet_points_for_top_articles(df: pd.DataFrame, column: str, top_n: int = 5) -> pd.DataFrame:
    """
    Generate bullet points summaries for the top N articles.
    
    Args:
        df (pd.DataFrame): DataFrame containing articles with GPT scores
        column (str): Name of the column containing article content
        top_n (int): Number of top articles to process
        
    Returns:
        pd.DataFrame: DataFrame with added bullet points for top articles
    """
    try:
        # Get top N articles
        top_articles = df[df['GPT_Pertinence'] > 7].head(5)
        
        print(f"📝 Generating bullet points for top {top_n} articles...")
        
        # Generate bullet points for each top article
        for idx, row in top_articles.iterrows():
            try:
                title = row.get('Title', '')
                content = row[column]
                if not content:
                    content = row["Summary"]
                bullet_points = generate_bullet_points_summary(title, content)
                df.at[idx, 'Bullet_Points'] = bullet_points
                print(f"✅ Generated bullet points for article: {title[:50]}...")
            except Exception as e:
                print(f"Error generating bullet points for article {idx}: {str(e)}")
                continue
                
        return df
        
    except Exception as e:
        print(f"❌ Error in generate_bullet_points_for_top_articles: {str(e)}")
        return df

def generate_linkedin_post(article: Dict) -> str:
    """
    Generate a LinkedIn post for an article using GPT.
    
    Args:
        article (Dict): Article data including title, summary, keywords, and URL
        
    Returns:
        str: Generated LinkedIn post
        
    Raises:
        OpenAIError: If the API request fails
    """
    try:
        prompt = LINKEDIN_PROMPT_TEMPLATE.format(
            title=article['Title'],
            summary=article['Summary'],
            keywords=article['Keywords'],
            url=article['URL']
        )

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,  # Slightly higher temperature for more creative writing
            max_tokens=800
        )
        
        return response.choices[0].message.content.strip()

    except Exception as e:
        raise OpenAIError(f"Failed to generate LinkedIn post: {str(e)}")