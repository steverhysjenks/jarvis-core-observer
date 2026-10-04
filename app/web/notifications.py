from html import escape

from app.storage.deliveries import (
    recent_deliveries,
)


def notification_history_html(
    limit: int = 10,
) -> str:
    deliveries = recent_deliveries(
        limit=limit
    )

    cards = []

    for delivery in deliveries:
        delivered_at = escape(
            delivery.get(
                "delivered_at",
                "",
            )
        )

        candidate_type = escape(
            delivery.get(
                "candidate_type"
            )
            or "Jarvis notification"
        )

        message = escape(
            delivery.get(
                "message",
                "",
            )
        )

        area = escape(
            delivery.get(
                "area"
            )
            or "Unknown area"
        )

        delivery_type = escape(
            delivery.get(
                "delivery_type",
                "unknown",
            )
        )

        cards.append(
            f"""
            <article class="notification">
                <div class="notification-header">
                    <div>
                        <div class="type">
                            {candidate_type}
                        </div>
                        <div class="meta">
                            {delivered_at}
                            · {area}
                        </div>
                    </div>

                    <span class="badge">
                        {delivery_type}
                    </span>
                </div>

                <div class="message">
                    {message}
                </div>
            </article>
            """
        )

    if not cards:
        cards.append(
            """
            <div class="empty">
                <h2>No notifications yet</h2>
                <p>
                    Successful Jarvis announcements
                    will appear here automatically.
                </p>
            </div>
            """
        )

    content = "\n".join(cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <title>Jarvis Notifications</title>

    <style>
        :root {{
            color-scheme: dark;
            font-family:
                Inter,
                system-ui,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;
        }}

        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            background: #0b0f14;
            color: #e6edf3;
        }}

        main {{
            width: min(900px, calc(100% - 32px));
            margin: 0 auto;
            padding: 40px 0 80px;
        }}

        header {{
            margin-bottom: 28px;
        }}

        h1 {{
            margin: 0 0 8px;
            font-size: 2rem;
        }}

        .subtitle {{
            margin: 0;
            color: #8b949e;
        }}

        .notification {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 14px;
        }}

        .notification-header {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: flex-start;
        }}

        .type {{
            font-weight: 650;
            text-transform: capitalize;
        }}

        .meta {{
            color: #8b949e;
            font-size: 0.88rem;
            margin-top: 4px;
        }}

        .message {{
            margin-top: 16px;
            line-height: 1.55;
            font-size: 1.05rem;
        }}

        .badge {{
            border: 1px solid #30363d;
            border-radius: 999px;
            padding: 4px 9px;
            color: #8b949e;
            font-size: 0.75rem;
            white-space: nowrap;
        }}

        .empty {{
            background: #161b22;
            border: 1px dashed #30363d;
            border-radius: 12px;
            padding: 40px 20px;
            text-align: center;
        }}

        .empty h2 {{
            margin-top: 0;
        }}

        .empty p {{
            color: #8b949e;
            margin-bottom: 0;
        }}

        footer {{
            margin-top: 28px;
            color: #6e7681;
            font-size: 0.8rem;
            text-align: center;
        }}
    </style>
</head>

<body>
    <main>
        <header>
            <h1>Jarvis Notifications</h1>

            <p class="subtitle">
                Recent messages delivered by Jarvis
            </p>
        </header>

        {content}

        <footer>
            Showing up to {limit} recent notifications
        </footer>
    </main>
</body>
</html>
"""
