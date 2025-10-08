"""
Custom Entity Type Definitions for Graphiti Knowledge Graph

Validated on 2025-10-04: Reduced extraction from 14→3 entities per episode.
100% deduplication. No noise entities.

Used across all sync paths: batch sync, webhooks, direct sync.
"""

from pydantic import BaseModel, Field


class Company(BaseModel):
    """
    A business organization or corporation with a legitimate business name.

    CRITICAL RULES - INCLUDE ONLY:
    - Real company names with proper nouns (e.g., "Acme Corporation", "Google LLC", "Microsoft")
    - Organizations with employees and business operations
    - Must be a recognizable business entity, NOT a URL, link text, or placeholder

    CRITICAL RULES - ALWAYS EXCLUDE:
    - Text containing "URL" (these are link placeholders, not companies)
    - Domain names alone (acme.com) - extract as domain attribute instead
    - Email addresses
    - Website URLs or LinkedIn profiles
    - Link text or navigation elements
    - Industry categories
    - Physical locations
    - Generic terms like "View Group", "Click here", etc.

    Extract domain, industry, location as ATTRIBUTES of the Company, not separate entities.
    """
    domain: str | None = Field(None, description="Company's primary domain (e.g., acme.com)")
    industry: str | None = Field(None, description="Industry or sector")
    location: str | None = Field(None, description="Primary office location")


class Contact(BaseModel):
    """
    A real person with a full name, typically in a professional context.

    CRITICAL RULES - INCLUDE ONLY:
    - Full names of real people (e.g., "Sarah Johnson", "John Smith", "Alex Chen")
    - Must be an actual person, not a sender name or email display name
    - Individuals with identifiable professional roles

    CRITICAL RULES - ALWAYS EXCLUDE:
    - Email display names (e.g., "AI Automation Society (Skool)" is a sender, not a person)
    - Email addresses alone (extract as email attribute)
    - Phone numbers alone (extract as phone attribute)
    - LinkedIn URLs or social profiles
    - Job titles without names (e.g., just "CFO" or "VP of Sales")
    - Generic role descriptions
    - Sender names from emails (extract from sender field, not content)

    Extract email, phone, title as ATTRIBUTES of the Contact, not separate entities.
    """
    email: str | None = Field(None, description="Contact's email address")
    phone: str | None = Field(None, description="Contact's phone number")
    title: str | None = Field(None, description="Job title or role")


class Deal(BaseModel):
    """
    A sales opportunity or business transaction with a name.

    INCLUDE:
    - Named sales opportunities (e.g., "Q4 Enterprise License - Acme Corp")
    - Business transactions with identifiers
    - Specific deals with context

    EXCLUDE:
    - Money amounts alone (e.g., "$250,000")
    - Deal stage names alone (e.g., "Negotiation")
    - Generic product names without deal context
    - Individual contract terms

    Extract amount, stage, products as ATTRIBUTES, not separate entities.
    """
    amount: int | None = Field(None, description="Deal value in dollars")
    stage: str | None = Field(None, description="Sales stage (e.g., 'Negotiation')")
    products: str | None = Field(None, description="Products or services in the deal")


# Entity type registry for Graphiti
ENTITY_TYPES = {
    "Company": Company,
    "Contact": Contact,
    "Deal": Deal
}

# Exclude generic "Entity" type to force LLM to use specific types
EXCLUDED_ENTITY_TYPES = ["Entity"]
