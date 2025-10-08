"""
Test the /api/process-emails endpoint with fake email data
"""

import asyncio
import httpx

# Test data - 3 fake emails
TEST_EMAILS = [
    {
        "id": "test_001",
        "subject": "Introduction to Acme Corp",
        "from_": "john.doe@acmecorp.com",
        "to": "alex@thunderbird-labs.com",
        "date": "2025-10-01 10:00:00",
        "body": """Hi Alex,

I'm John Doe, VP of Sales at Acme Corporation. We're a leading provider of cloud infrastructure solutions.

I'd love to discuss how we can help Thunderbird Labs scale their operations. We've worked with similar companies like TechStart Inc and CloudVentures.

Looking forward to connecting!

Best regards,
John Doe
VP of Sales, Acme Corp
john.doe@acmecorp.com
+1-555-0123"""
    },
    {
        "id": "test_002",
        "subject": "Follow-up on Partnership Opportunity",
        "from_": "sarah.miller@innovate.io",
        "to": "alex@thunderbird-labs.com",
        "date": "2025-10-02 14:30:00",
        "body": """Hi Alex,

It was great meeting you at the TechConf 2025 last week!

As discussed, Innovate.io is looking to partner with companies like Thunderbird Labs to expand our AI capabilities. We have a $2M deal on the table if we can finalize by Q4.

Can we schedule a call next week to discuss the details?

Thanks,
Sarah Miller
Partnership Director, Innovate.io
sarah.miller@innovate.io"""
    },
    {
        "id": "test_003",
        "subject": "Quarterly Report - Q3 2025",
        "from_": "finance@thunderbird-labs.com",
        "to": "alex@thunderbird-labs.com",
        "date": "2025-10-03 09:15:00",
        "body": """Alex,

Here's the Q3 financial summary:

Revenue: $450K (up 20% from Q2)
Expenses: $380K
Net: $70K

Key deals closed:
- Acme Corp: $150K/year contract
- DataFlow Systems: $80K implementation
- CloudVentures: $100K consulting

New leads in pipeline:
- Innovate.io: $2M potential
- TechStart Inc: $500K opportunity

Let me know if you want to review the details.

Best,
Finance Team"""
    }
]

async def test_endpoint():
    """Send test emails to the backend endpoint"""

    url = "http://localhost:8000/api/process-emails"

    payload = {
        "user_id": "test_user_001",  # Simple ID without hyphens to avoid RediSearch syntax error
        "emails": TEST_EMAILS
    }

    print(f"📧 Sending {len(TEST_EMAILS)} test emails to {url}")
    print()

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success!")
            print(f"   Status: {data['status']}")
            print(f"   Emails processed: {data['emails_processed']}")
            print(f"   Message: {data['message']}")
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"   {response.text}")

if __name__ == "__main__":
    asyncio.run(test_endpoint())
