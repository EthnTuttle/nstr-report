"""Fetch activity from bnoc.xyz Discourse forum."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape

import httpx


@dataclass
class Post:
    """A post within a topic."""

    id: int
    author: str
    content: str  # Plain text content
    created_at: datetime
    post_number: int


@dataclass
class Topic:
    """A topic from bnoc.xyz."""

    id: int
    title: str
    slug: str
    author: str
    posts_count: int
    last_posted_at: datetime
    bumped_at: datetime
    created_at: datetime
    tags: list[str]
    url: str
    posts: list[Post] = field(default_factory=list)

    @property
    def is_new(self) -> bool:
        """Check if topic was created recently (same day as last activity)."""
        return self.created_at.date() == self.bumped_at.date()


@dataclass
class Activity:
    """Activity summary from bnoc.xyz."""

    topics: list[Topic]
    fetched_at: datetime
    source_url: str


def parse_datetime(dt_str: str) -> datetime:
    """Parse ISO datetime string to datetime object."""
    dt_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(dt_str)


def html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    # Remove image tags but keep alt text
    text = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r'[\1]', html)
    # Remove all other HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Unescape HTML entities
    text = unescape(text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_topic_posts(
    source_url: str,
    topic_id: int,
    topic_slug: str,
    since: datetime,
) -> list[Post]:
    """Fetch posts for a specific topic that are newer than since."""
    response = httpx.get(
        f"{source_url}/t/{topic_slug}/{topic_id}.json",
        headers={"Accept": "application/json"},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()

    posts = []
    for post_data in data.get("post_stream", {}).get("posts", []):
        created_at = parse_datetime(post_data["created_at"])

        # Only include posts from the lookback period
        if created_at >= since:
            content = html_to_text(post_data.get("cooked", ""))
            post = Post(
                id=post_data["id"],
                author=post_data["username"],
                content=content,
                created_at=created_at,
                post_number=post_data["post_number"],
            )
            posts.append(post)

    return posts


def fetch_activity(source_url: str, lookback_hours: int = 24) -> Activity:
    """Fetch recent activity from bnoc.xyz.

    Args:
        source_url: Base URL of the Discourse forum
        lookback_hours: Number of hours to look back for activity

    Returns:
        Activity object with recent topics and their posts
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Fetch the latest topics JSON
    response = httpx.get(
        f"{source_url}/latest.json",
        headers={"Accept": "application/json"},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()

    # Build user lookup
    users = {u["id"]: u["username"] for u in data.get("users", [])}

    # Filter topics with recent activity
    recent_topics = []
    for topic_data in data.get("topic_list", {}).get("topics", []):
        bumped_at = parse_datetime(topic_data["bumped_at"])

        if bumped_at >= cutoff:
            # Find the original poster
            posters = topic_data.get("posters", [])
            author = "unknown"
            for poster in posters:
                if "Original Poster" in poster.get("description", ""):
                    author = users.get(poster["user_id"], "unknown")
                    break

            topic = Topic(
                id=topic_data["id"],
                title=topic_data["title"],
                slug=topic_data["slug"],
                author=author,
                posts_count=topic_data["posts_count"],
                last_posted_at=parse_datetime(topic_data["last_posted_at"]),
                bumped_at=bumped_at,
                created_at=parse_datetime(topic_data["created_at"]),
                tags=topic_data.get("tags", []),
                url=f"{source_url}/t/{topic_data['slug']}/{topic_data['id']}",
            )

            # Fetch the actual posts for this topic
            topic.posts = fetch_topic_posts(
                source_url, topic.id, topic.slug, cutoff
            )

            recent_topics.append(topic)

    # Sort by most recent activity first
    recent_topics.sort(key=lambda t: t.bumped_at, reverse=True)

    return Activity(
        topics=recent_topics,
        fetched_at=datetime.now(timezone.utc),
        source_url=source_url,
    )
