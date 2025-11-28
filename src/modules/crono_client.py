"""
Crono CRM API Client
Integrates with Crono to create meeting notes and activities
"""

import os
import requests
from typing import Optional, Dict, List
from datetime import datetime


class CronoClient:
    def __init__(self, api_key: Optional[str] = None, public_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize Crono API client

        Args:
            api_key: Crono private API key (or from CRONO_API_KEY env var)
            public_key: Crono public API key (or from CRONO_PUBLIC_KEY env var)
            base_url: API base URL (or from CRONO_API_URL env var)
        """
        self.api_key = api_key or os.getenv('CRONO_API_KEY')
        self.public_key = public_key or os.getenv('CRONO_PUBLIC_KEY')
        # Updated to correct Crono API base URL (v1, not api/v1)
        self.base_url = base_url or os.getenv('CRONO_API_URL', 'https://ext.crono.one/v1')

        if not self.api_key or not self.public_key:
            raise ValueError("Both CRONO_API_KEY (private) and CRONO_PUBLIC_KEY are required.")

        self.headers = {
            "X-Api-Key": self.public_key,
            "X-Api-Secret": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def search_accounts(self, query: str = None, domain: str = None, limit: int = 10) -> List[Dict]:
        """
        Search for accounts/companies in Crono

        Args:
            query: Search query (company name)
            domain: Company domain (will match against website field)
            limit: Max results

        Returns:
            List of matching accounts
        """
        try:
            # Use GET /Accounts (plural) endpoint
            params = {}
            if limit:
                params['limit'] = limit
            if query:
                params['search'] = query

            response = requests.get(
                f"{self.base_url}/Accounts",
                headers=self.headers,
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                # Response might be direct array or object with data field
                data = response.json()
                if isinstance(data, list):
                    accounts = data
                else:
                    accounts = data.get('data', data.get('accounts', []))

                # If searching by domain, filter by website field
                if domain and accounts:
                    return self._filter_by_website_domain(accounts, domain)
                return accounts
            else:
                print(f"API returned status {response.status_code}: {response.text[:200]}")
                return []

        except Exception as e:
            print(f"Error searching accounts: {e}")
            return []

    def search_accounts_by_name(self, company_name: str) -> Optional[Dict]:
        """
        Search for account by exact company name using POST /api/v1/Accounts/search

        Args:
            company_name: Company name to search for

        Returns:
            Account dict if found, None otherwise
        """
        try:
            # Use POST /api/v1/Accounts/search with "name" parameter
            # This works better than the "search" parameter
            payload = {"name": company_name}

            # Hardcode the API URL for this specific search endpoint as it's inconsistent
            api_url = "https://ext.crono.one/api/v1"

            response = requests.post(
                f"{api_url}/Accounts/search",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                accounts = data.get('data', [])

                if isinstance(accounts, list) and len(accounts) > 0:
                    # Return first match
                    return accounts[0]

            return None

        except Exception as e:
            print(f"Error searching accounts by name: {e}")
            return None

    def _check_domain_mapping(self, email_domain: str) -> Optional[str]:
        """
        Check if email domain has a manually configured account mapping.

        Args:
            email_domain: Email domain to check

        Returns:
            Account ID if mapped, None otherwise
        """
        import json
        import os

        mapping_file = os.path.join(os.path.dirname(__file__), '..', 'account_mappings.json')

        try:
            if os.path.exists(mapping_file):
                with open(mapping_file, 'r') as f:
                    mappings = json.load(f)

                domain_map = mappings.get('domain_to_account', {})
                # Normalize domain (lowercase, no www)
                normalized_domain = email_domain.lower().replace('www.', '')

                return domain_map.get(normalized_domain)
        except Exception as e:
            print(f"Warning: Could not read account mappings: {e}")

        return None

    def _filter_by_website_domain(self, accounts: List[Dict], target_domain: str) -> List[Dict]:
        """
        Filter accounts by comparing website field domain with target domain

        Args:
            accounts: List of account objects
            target_domain: Domain to match (e.g., "acmecorp.com")

        Returns:
            Filtered list of accounts with matching website domain
        """
        import re
        from urllib.parse import urlparse

        matching_accounts = []

        # Normalize target domain (remove www, lowercase)
        target_domain_clean = target_domain.lower().replace('www.', '')

        for account in accounts:
            website = account.get('website', '') or account.get('Website', '')

            if not website:
                continue

            try:
                # Parse website URL to extract domain
                # Handle cases: "acmecorp.com", "www.acmecorp.com", "https://acmecorp.com"
                if not website.startswith(('http://', 'https://')):
                    website = 'https://' + website

                parsed = urlparse(website)
                website_domain = parsed.netloc.lower().replace('www.', '')

                # Match if domains are the same
                if website_domain == target_domain_clean:
                    matching_accounts.append(account)

            except Exception as e:
                # If parsing fails, try simple string comparison
                website_clean = website.lower().replace('http://', '').replace('https://', '').replace('www.', '').strip('/')
                if target_domain_clean in website_clean or website_clean in target_domain_clean:
                    matching_accounts.append(account)

        return matching_accounts

    def get_account_by_id(self, account_id: str) -> Optional[Dict]:
        """Get account details by ID"""
        try:
            # Use Accounts/{objectId} endpoint
            params = {
                'WithExternalValuesNoTags': 'true',
                'WithTags': 'true',
                'WithTasks': 'true'
            }
            response = requests.get(
                f"{self.base_url}/Accounts/{account_id}",
                headers=self.headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching account: {e}")
            return None

    def create_note(
        self,
        account_id: str,
        description: str,
        opportunity_id: Optional[str] = None,
        prospect_ids: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Create a note on an account using the Crono v1 API

        Args:
            account_id: Crono account ID (objectId)
            description: Note description/content (supports HTML)
            opportunity_id: Optional opportunity ID
            prospect_ids: Optional list of prospect IDs

        Returns:
            Note objectId if successful, None otherwise
        """
        try:
            # Crono API v1 format
            payload = {
                "data": {
                    "description": description,
                    "accountId": account_id,
                    "opportunityId": opportunity_id,
                    "prospectIds": prospect_ids or []
                }
            }

            response = requests.post(
                f"{self.base_url}/Notes",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            # Check response
            if response.status_code in [200, 201]:
                result = response.json()

                # Check if API returned success
                if result.get('isSuccess'):
                    # The API returns success but does not return the note's objectId.
                    # We return the account_id to confirm success to the caller.
                    note_data = result.get('data', {})
                    account_id_from_response = note_data.get('accountId')

                    print(f"✅ Note created successfully in Crono")
                    print(f"   Account ID: {account_id_from_response}")

                    return account_id_from_response
                else:
                    errors = result.get('errors', [])
                    print(f"❌ Crono API returned isSuccess=false")
                    print(f"   Errors: {errors}")
                    return None
            else:
                print(f"❌ Crono API returned status {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                return None

        except Exception as e:
            print(f"Error creating note: {e}")
            import traceback
            traceback.print_exc()
            return None

    def create_meeting_summary(
        self,
        account_id: str,
        meeting_title: str,
        summary_data: Dict,
        meeting_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a structured meeting summary note

        Args:
            account_id: Crono account ID
            meeting_title: Meeting title
            summary_data: Dict with tech_stack, pain_points, impact, next_steps, roadblocks
            meeting_url: Optional Fathom meeting URL

        Returns:
            Note ID if successful
        """
        # Build plain text content for note (no HTML tags)
        content = f"""🎯 Meeting Summary: {meeting_title}

💻 Tech Stack
{summary_data.get('tech_stack', 'N/A')}

⚠️ Pain Points
{summary_data.get('pain_points', 'N/A')}

📊 Impact of Pain
{summary_data.get('impact', 'N/A')}

✅ Next Steps
{summary_data.get('next_steps', 'N/A')}

🚧 Roadblocks
{summary_data.get('roadblocks', 'N/A')}"""

        if meeting_url:
            content += f'\n\n🎥 View Full Meeting Recording: {meeting_url}'

        return self.create_note(
            account_id=account_id,
            description=content,
            opportunity_id=None,
            prospect_ids=[]
        )

    def search_opportunities(self, account_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        Search for opportunities (deals) using POST /api/v1/Opportunities/search endpoint.

        Args:
            account_id: The Crono account ID (objectId). If None, searches all opportunities.
            limit: Maximum number of opportunities to return (default 100).
            offset: Number of opportunities to skip for pagination (default 0).

        Returns:
            List of matching opportunity dictionaries.
        """
        try:
            # Use /api/v1 base URL for search endpoint (different from /v1)
            api_url = "https://ext.crono.one/api/v1"

            payload = {
                "pagination": {
                    "limit": limit,
                    "offset": offset
                },
                "includes": {
                    "withAccount": None
                },
                "objectIds": [],
                "createdDateMin": None,
                "createdDateMax": None,
                "lastModifiedDateMin": None,
                "lastModifiedDateMax": None,
                "closeDateMin": None,
                "closeDateMax": None,
                "isWon": None,
                "isClosed": None,
                "amountMin": None,
                "amountMax": None,
                "name": None,
                "stage": None,
                "pipeline": None,
                "active": None,
                "accountId": account_id,  # Filter by account ID
                "userId": None,
                "year": None,
                "externalProperties": [],
                "sort": None
            }

            response = requests.post(
                f"{api_url}/Opportunities/search",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                opportunities = data.get('data', []) if isinstance(data, dict) else data
                return opportunities
            else:
                print(f"Error searching opportunities: {response.status_code} - {response.text[:200]}")
                return []

        except Exception as e:
            print(f"Error searching opportunities: {e}")
            return []

    def get_deals_for_account(self, account_id: Optional[str] = None) -> List[Dict]:
        """
        Get deals (opportunities) for a specific account.

        Args:
            account_id: The Crono account ID (objectId). If None, fetches all opportunities.

        Returns:
            List of deal dictionaries.
        """
        return self.search_opportunities(account_id=account_id, limit=100)

    def find_account_by_domain(self, email_domain: str, company_name: str = None) -> Optional[Dict]:
        """
        Find account by email domain (checks website field) or company name.
        Uses a multi-strategy approach to increase the chance of finding a match.

        Args:
            email_domain: Email domain (e.g., "acmecorp.com")
            company_name: Optional company name for fallback searches.

        Returns:
            Account dict if found, None otherwise
        """
        # Normalize domain for consistent matching
        normalized_email_domain = email_domain.lower().replace('www.', '')
        
        # Strategy 0: Check local account mappings first (for accounts beyond API limit)
        mapped_value = self._check_domain_mapping(normalized_email_domain)
        if mapped_value:
            print(f"✅ Found account in local mapping for {normalized_email_domain}: {mapped_value}")

            # Check if it's an objectId (contains underscore) or company name
            if '_' in mapped_value:
                # It's an objectId - try GET /Accounts/{id}
                print(f"   Treating as objectId, fetching account...")
                account = self.get_account_by_id(mapped_value)
                if account:
                    return account
                else:
                    print(f"⚠️  Mapped account ID {mapped_value} not found in Crono. Falling back to API search.")
            else:
                # It's a company name - use POST search
                print(f"   Treating as company name, using POST search...")
                account = self.search_accounts_by_name(mapped_value)
                if account:
                    print(f"✅ Found account via POST search: {account.get('name')} ({account.get('objectId')})")
                    return account
                else:
                    print(f"⚠️  Mapped company name '{mapped_value}' not found in Crono. Falling back to API search.")

        # Strategy 1: Search all recent accounts (max 200) and filter by website domain
        print(f"🔍 Strategy 1: Searching recent 200 accounts by domain {normalized_email_domain}")
        accounts_from_search = self.search_accounts(limit=200)  # Fetch max accounts allowed by API
        domain_matches = self._filter_by_website_domain(accounts_from_search, normalized_email_domain)

        if domain_matches:
            print(f"✅ Strategy 1 matched account by domain: {domain_matches[0].get('name')} ({domain_matches[0].get('objectId')})")
            return domain_matches[0]  # Return first match

        # --- Fallback strategies using company_name if provided ---
        if company_name:
            print(f"🔍 No match from Strategy 1. Trying company name searches for '{company_name}'.")

            # Prepare name variations for robust search
            name_variations = [company_name]
            if company_name.islower() or company_name.isupper():
                name_variations.append(company_name.capitalize())
            else:
                name_variations.append(company_name.lower())
                name_variations.append(company_name.upper())
            name_variations = list(set(name_variations)) # Remove duplicates

            for name_var in name_variations:
                # Strategy 2: Try POST search by company name (more accurate)
                print(f"🔍 Strategy 2: Trying POST search by exact name '{name_var}'")
                account = self.search_accounts_by_name(name_var)
                if account:
                    print(f"✅ Strategy 2 matched account by exact name: {account.get('name')} ({account.get('objectId')})")
                    return account

            for name_var in name_variations:
                # Strategy 3: Try GET search by company name as fallback (less accurate)
                print(f"🔍 Strategy 3: Trying GET search by name '{name_var}' (fallback)")
                accounts_from_query = self.search_accounts(query=name_var, limit=10)

                if accounts_from_query:
                    # First pass: Look for EXACT matches only (prioritize exact over partial)
                    for acc in accounts_from_query:
                        acc_name = acc.get('name', '').lower()
                        if name_var.lower() == acc_name:
                            print(f"✅ Strategy 3 matched account by exact name: {acc.get('name')} ({acc.get('objectId')})")
                            return acc

                    # Second pass: Look for substring matches (less reliable)
                    for acc in accounts_from_query:
                        acc_name = acc.get('name', '').lower()
                        if name_var.lower() in acc_name:
                            print(f"⚠️  Strategy 3 matched account by partial name: {acc.get('name')} ({acc.get('objectId')})")
                            print(f"   WARNING: This is a partial match, may not be accurate!")
                            return acc

                    # If no exact or substring match, return first result
                    if accounts_from_query:
                        print(f"✅ Strategy 3 (fallback) matched account by query: {accounts_from_query[0].get('name')} ({accounts_from_query[0].get('objectId')})")
                        return accounts_from_query[0]

        # No match found after trying all strategies
        print(f"❌ No Crono account found for domain '{normalized_email_domain}' or company '{company_name}'.")
        return None

    def find_or_prompt_account(self, company_name: str) -> Optional[str]:
        """
        Find account by company name or return None if not found
        (Legacy method - use find_account_by_domain for better results)

        Args:
            company_name: Company name to search

        Returns:
            Account objectId if found, None otherwise
        """
        accounts = self.search_accounts(query=company_name, limit=5)

        if not accounts:
            return None

        if len(accounts) == 1:
            return accounts[0].get('objectId')

        # Multiple matches - return best match or None
        for account in accounts:
            name = account.get('name', '').lower()
            if company_name.lower() in name or name in company_name.lower():
                return account.get('objectId')

        return None


if __name__ == "__main__":
    # Test the client
    from dotenv import load_dotenv
    load_dotenv()

    try:
        client = CronoClient()

        # Get a test account
        print("Testing account search...")
        accounts = client.search_accounts(query="NeuronUP", limit=1)
        if not accounts:
            # Fallback to a generic search if NeuronUP is not found
            accounts = client.search_accounts(limit=1)
            if not accounts:
                raise Exception("No test account found.")

        account = accounts[0]
        account_id = account.get('objectId')
        print(f"✅ Found test account: {account.get('name')} ({account_id})")

        # Test creating a note
        print("\nTesting note creation...")
        summary_data = {
            "tech_stack": "Node.js, React, PostgreSQL",
            "pain_points": "Manual lead generation taking 10h/week",
            "impact": "€50K lost revenue per quarter",
            "next_steps": "Trial starting next Monday, onboarding call scheduled",
            "roadblocks": "Budget approval needed"
        }

        note_id = client.create_meeting_summary(
            account_id=account_id,
            meeting_title="Discovery Call",
            summary_data=summary_data,
            meeting_url="https://fathom.video/share/example"
        )

        if note_id:
            print(f"✅ Note created: {note_id}")
        else:
            print("⚠️  Note creation failed.")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()