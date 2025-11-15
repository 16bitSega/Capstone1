import streamlit as st
import os
import logging
import pandas as pd
import numpy as np
import re
from dotenv import load_dotenv
from google import genai

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

logging.basicConfig(level=logging.INFO)

DATA_PATH = "ai_job_market.csv"
df = pd.read_csv(DATA_PATH)

# Sidebar dataset highlights
st.sidebar.header("Dataset Highlights")
st.sidebar.markdown("**Experience Levels**")
st.sidebar.write("Entry, Junior, Middle, Senior, Lead")
st.sidebar.markdown("**Job Roles**")
roles_sidebar = [
    "AI Product Manager",
    "AI Researcher",
    "Computer Vision Engineer",
    "Data Analyst",
    "Data Scientist",
    "ML Engineer",
    "NLP Engineer",
    "Quant Researcher"
]
for role in roles_sidebar:
    st.sidebar.write(f"- {role}")

def parse_salary_range(salary_range_str):
    try:
        min_str, max_str = salary_range_str.split('-')
        return int(min_str.strip()), int(max_str.strip())
    except Exception:
        return np.nan, np.nan

df[['salary_min', 'salary_max']] = df['salary_range_usd'].apply(
    lambda x: pd.Series(parse_salary_range(x))
)

client = genai.Client()

def smart_filter(df, col, keyword):
    if not keyword:
        return df
    pattern = '|'.join([
        re.sub(r's$', '', keyword.lower()).replace(' ', ''),
        keyword.lower().replace(' ', ''),
        keyword.lower(),
        keyword.lower().rstrip('s'),
    ])
    return df[df[col].str.replace(' ', '').str.lower().str.contains(pattern, na=False)]

def aggregate_skills_tools(exp_level, role_keyword):
    df_filtered = smart_filter(df, 'job_title', role_keyword)
    if exp_level:
        df_filtered = df_filtered[df_filtered['experience_level'].str.lower().str.contains(exp_level.lower())]
    logging.info(f"Filtered {len(df_filtered)} rows for role '{role_keyword}' and level '{exp_level}'. Sample: {df_filtered[['job_title','experience_level']].head(5).to_dict('records')}")
    skills_series = df_filtered['skills_required'].dropna().str.split(', ').explode()
    tools_series = df_filtered['tools_preferred'].dropna().str.split(', ').explode()
    top_skills = skills_series.value_counts().head(10).index.tolist()
    top_tools = tools_series.value_counts().head(10).index.tolist()
    logging.info(f"Extracted skills: {top_skills}")
    logging.info(f"Extracted tools: {top_tools}")
    return top_skills, top_tools

def avg_salary(exp_level, role_keyword):
    df_filtered = smart_filter(df, 'job_title', role_keyword)
    if exp_level:
        df_filtered = df_filtered[df_filtered['experience_level'].str.lower().str.contains(exp_level.lower())]
    avg_min = df_filtered['salary_min'].mean()
    avg_max = df_filtered['salary_max'].mean()
    logging.info(f"SALARY: {len(df_filtered)} rows for '{role_keyword}' '{exp_level}'. Sample: {df_filtered[['job_title','experience_level','salary_range_usd']].head(5).to_dict('records')}")
    logging.info(f"SALARY min: {avg_min}, max: {avg_max}")
    if pd.isna(avg_min) or pd.isna(avg_max):
        return "No salary data found for this query."
    return f"Average salary for {role_keyword or 'all roles'} ({exp_level or 'all levels'}): ${int(avg_min)}-${int(avg_max)} USD"

def industry_distribution():
    dist = df['industry'].value_counts().sort_values(ascending=False)
    summary = ', '.join([f"{k}: {v}" for k,v in dist.head(5).items()])
    logging.info(f"Industry distribution: {summary}")
    return summary

def skills_overlap(role1, level1, role2, level2):
    df_r1 = df[
        (df['job_title'].str.lower().str.contains(role1.lower())) &
        (df['experience_level'].str.lower().str.contains(level1.lower()))
    ]
    df_r2 = df[
        (df['job_title'].str.lower().str.contains(role2.lower())) &
        (df['experience_level'].str.lower().str.contains(level2.lower()))
    ]
    s1 = set(df_r1['skills_required'].dropna().str.cat(sep=', ').split(', '))
    s2 = set(df_r2['skills_required'].dropna().str.cat(sep=', ').split(', '))
    overlap = s1.intersection(s2)
    logging.info(f"Skills for '{level1} {role1}': {s1}")
    logging.info(f"Skills for '{level2} {role2}': {s2}")
    logging.info(f"Skills overlap: {overlap}")
    return f"Skills overlapping between {level1} {role1} and {level2} {role2}: {', '.join(sorted(overlap)) if overlap else 'No overlap found.'}"

def extract_role_and_level(phrase):
    levels = ['entry', 'junior', 'middle', 'senior', 'lead']
    tokens = phrase.lower().split()
    level = [l for l in levels if l in tokens]
    level = level[0] if level else ""
    # Remove the level token from the phrase to get the role
    role = " ".join([t for t in tokens if t not in levels])
    return role, level

def parse_roles_and_levels(question_lower):
    levels = ['entry', 'junior', 'middle', 'senior', 'lead']
    roles = [r.lower() for r in [
        'ai engineer', 'machine learning engineer', 'ml engineer',
        'data scientist', 'data analyst', 'nlp engineer',
        'computer vision engineer', 'quant researcher',
        'ai researcher', 'ai product manager'
    ]]
    level = next((w for w in levels if w in question_lower), None)
    role_found = next((r for r in roles if r in question_lower), None)
    return level, role_found

def create_prompt_context(user_question):
    question_lower = user_question.lower()
    level, role_found = parse_roles_and_levels(question_lower)
    # Salary extraction
    if any(x in question_lower for x in ['salary', 'pay', 'earnings', 'compensation']):
        salary_info = avg_salary(level, role_found)
        return f"Data-driven answer: {salary_info}\nUser question: {user_question}"
    # Skills overlap extraction
    if 'skills overlap' in question_lower:
        roles_query = re.findall(r'between ([\w\s]+) and ([\w\s]+)', question_lower)
        if roles_query:
            r1_phrase, r2_phrase = roles_query[0]
            role1, level1 = extract_role_and_level(r1_phrase.strip())
            role2, level2 = extract_role_and_level(r2_phrase.strip())
            overlap_text = skills_overlap(role1, level1, role2, level2)
            return f"Short answer. {overlap_text}\nUser question: {user_question}"
        else:
            return f"Specify two roles for skills overlap. User question: {user_question}"
    # Skills/tools extraction
    if any(x in question_lower for x in ['skills', 'tools', 'requirements']):
        skills, tools = aggregate_skills_tools(level, role_found)
        context = f"Top skills: {', '.join(skills)}; top tools: {', '.join(tools)}"
        return f"Brief data-driven summary. {context}\nUser question: {user_question}"
    # Industry dist
    if 'industry' in question_lower:
        summary = industry_distribution()
        return f"Industries hiring most: {summary}\nUser question: {user_question}"
    return f"Answer concisely. User question: {user_question}"

def ask_gemini_with_context(user_question: str):
    with st.spinner('...searching DB for related queries...'):
        prompt = create_prompt_context(user_question)
    with st.spinner('...gathering information and enhancing with LLM...'):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return response.text
        except Exception as e:
            logging.error(f"Google Gemini API failed: {e}")
            return "Failed to fetch answer from Gemini API."

def create_github_issue(title: str, body: str):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        st.error("GitHub token or repository config missing in .env")
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    data = {"title": title, "body": body}
    try:
        import requests
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json().get("html_url")
    except Exception as e:
        logging.error(f"GitHub Issue Creation failed: {e}")
        st.error(f"Failed to create issue: {e}")
        return None

st.title("Chat with Data: AI Engineering Job Market Insights")

st.markdown("""
Welcome! This app leverages a comprehensive dataset of AI engineering job market data for 2025 to provide data-driven insights on skills, salaries, tools, industries, and roles.

You can explore the data with natural language questions such as salary info, required skills, tools per role and level, industry demand, and skill overlaps.

---

### Example questions
""")

example_questions = [
    "Which industries demand AI Researcher most?",
    "What skills are required on middle ML engineer position?",
    "What is an average salary of the Data Analyst?",
    "Which tools are required on senior level position in AI Product Manager?",
    "What skills overlap between entry NLP Engineer and middle AI Product Manager?",
]

for q in example_questions:
    st.markdown(f"- {q}")

user_question = st.text_input("Enter your question here")
if st.button("Ask Agent"):
    if not user_question.strip():
        st.warning("Please enter a valid question")
    else:
        answer = ask_gemini_with_context(user_question)
        st.markdown("### Agent Answer")
        st.write(answer)
        logging.info(f"User question: {user_question}")
        logging.info(f"Agent answer: {answer}")

st.markdown("---")
st.markdown("### Create Support Ticket")
issue_title = st.text_input("Issue Title", key="title")
issue_body = st.text_area("Issue Description", key="body")
if st.button("Create Ticket"):
    if not issue_title.strip() or not issue_body.strip():
        st.warning("Both title and description are required.")
    else:
        url = create_github_issue(issue_title.strip(), issue_body.strip())
        if url:
            st.success(f"Issue created successfully! [View on GitHub]({url})")

st.info("Safety: Destructive operations are disabled and not supported.")
