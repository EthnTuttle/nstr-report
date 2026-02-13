"""Format activity into Nostr-ready text."""

from datetime import datetime, timezone

import anthropic

from .fetcher import Activity, Topic


NSTR_MESSAGE = "NSTR - Nothing Significant to Report"


def format_topic_list(activity: Activity) -> str:
    """Format the list of active topics."""
    lines = []
    for topic in activity.topics:
        tag_str = f" [{', '.join(topic.tags)}]" if topic.tags else ""
        new_marker = " [NEW]" if topic.is_new else ""
        post_count = len(topic.posts)
        lines.append(
            f"  {topic.title}{tag_str}{new_marker} "
            f"({post_count} new post{'s' if post_count != 1 else ''})"
        )
        lines.append(f"    {topic.url}")
    return "\n".join(lines)


def format_posts_for_llm(activity: Activity) -> str:
    """Format all posts for LLM consumption."""
    sections = []

    for topic in activity.topics:
        section_lines = [
            f"## Topic: {topic.title}",
            f"Tags: {', '.join(topic.tags) if topic.tags else 'none'}",
            f"URL: {topic.url}",
            "",
        ]

        for post in topic.posts:
            timestamp = post.created_at.strftime("%Y-%m-%d %H:%M UTC")
            section_lines.append(f"### Post by {post.author} ({timestamp}):")
            section_lines.append(post.content)
            section_lines.append("")

        sections.append("\n".join(section_lines))

    return "\n---\n\n".join(sections)


def generate_summary_with_claude(activity: Activity, api_key: str) -> str:
    """Generate a comprehensive summary using Claude API.

    Args:
        activity: The activity to summarize
        api_key: Anthropic API key

    Returns:
        A summary of the discussions
    """
    posts_text = format_posts_for_llm(activity)
    topic_count = len(activity.topics)
    post_count = sum(len(t.posts) for t in activity.topics)

    prompt = f"""You are summarizing daily activity from the Bitcoin Network Operations Collective (BNOC) forum - a technical forum for Bitcoin network operators and developers.

In the past 24 hours, there were {post_count} new posts across {topic_count} topic(s).

Here is the full content of the discussions:

{posts_text}

Write a concise but informative summary for Bitcoin developers and network operators. Include:
1. Key observations or findings reported
2. Any security concerns or attacks discussed
3. Notable technical details or data shared
4. Action items or recommendations if any

Keep the summary under 280 characters if there's only 1-2 posts, otherwise keep it under 500 characters. Be direct and technical. Do not use emojis. Do not use markdown formatting."""

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text.strip()


def format_activity(activity: Activity, anthropic_api_key: str | None = None) -> str:
    """Format activity into a Nostr-ready message.

    Args:
        activity: The fetched activity
        anthropic_api_key: Optional API key for Claude summary generation

    Returns:
        Formatted message string
    """
    if not activity.topics:
        return NSTR_MESSAGE

    date_str = activity.fetched_at.strftime("%Y-%m-%d")
    topic_count = len(activity.topics)
    post_count = sum(len(t.posts) for t in activity.topics)

    # If we have Claude, generate a proper summary
    if anthropic_api_key and post_count > 0:
        try:
            summary = generate_summary_with_claude(activity, anthropic_api_key)
            lines = [
                f"BNOC Daily Summary ({date_str})",
                "",
                summary,
                "",
                "Topics:",
                format_topic_list(activity),
                "",
                f"Source: {activity.source_url}",
            ]
            return "\n".join(lines)
        except Exception as e:
            print(f"Warning: Could not generate summary: {e}")

    # Fallback: simple list without AI summary
    topic_word = "topic" if topic_count == 1 else "topics"
    lines = [
        f"BNOC Daily Summary ({date_str})",
        "",
        f"{topic_count} {topic_word} with activity:",
        "",
        format_topic_list(activity),
        "",
        f"Source: {activity.source_url}",
    ]

    return "\n".join(lines)
