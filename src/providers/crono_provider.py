"""
Crono CRM Provider Implementation

Implements the CRMProvider interface for Crono CRM.
Wraps the existing Crono API client logic to conform to the standard provider interface.
"""

import os
import json
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from urllib.parse import urlparse

from .base_provider import CRMProvider
from ..exceptions import CRMIntegrationError


class CronoProvider(CRMProvider):
    """Crono CRM provider implementation.

    This provider integrates with Crono CRM API, implementing all methods
    defined in the CRMProvider abstract base class.
    """

    def __init__(self, credentials: Dict[str, Any]):
        """Initialize Crono API provider.

        Args:
            credentials: Dict containing:
                - 'public_key': Crono public API key
                - 'private_key': Crono private API key (secret)
                - 'base_url': Optional API base URL (defaults to Crono production)
        """
        self.public_key = credentials.get('public_key')
        self.private_key = credentials.get('private_key')
        self.base_url = credentials.get('base_url', 'https://ext.crono.one/api/v1')

        if not self.public_key or not self.private_key:
            raise ValueError("Crono provider requires 'public_key' and 'private_key' credentials")

        self.headers = {
            "x-api-key": self.public_key,
            "x-api-secret": self.private_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # ASSUMPTION: Account mappings file location is relative to project root
        # This maintains backward compatibility with existing account_mappings.json
        self.account_mappings_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'configs', 'account_mappings.json'
        )

    def search_prospects(self, query: str = "", account_id: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Search for prospects/contacts in Crono.

        Args:
            query: Search query (contact name)
            account_id: Filter by account ID
            limit: Max results (target, not API limit)

        Returns:
            List of standardized prospect dicts
        """
        try:
            # Use POST /api/v1/Prospects/search for proper filtering
            api_url = "https://ext.crono.one/api/v1"

            # Crono API has a max limit of 50 per request
            # We'll paginate to get more results
            api_limit = 50
            max_pages = 10  # Max 500 prospects total
            all_prospects = []

            for page in range(max_pages):
                payload = {
                    "pagination": {
                        "limit": api_limit,
                        "offset": page * api_limit
                    }
                }

                # Add name filter if specified (server-side search)
                if query:
                    payload["name"] = query

                # Add accountId filter if specified
                if account_id:
                    payload["accountId"] = account_id

                import sys
                sys.stderr.write(f"  [API REQUEST] POST {api_url}/Prospects/search\n")
                sys.stderr.write(f"  [API PAYLOAD] {json.dumps(payload, indent=2)}\n")
                sys.stderr.write(f"  [API HEADERS] {json.dumps({k: v for k, v in self.headers.items() if k != 'X-API-SECRET'}, indent=2)}\n")

                response = requests.post(
                    f"{api_url}/Prospects/search",
                    headers=self.headers,
                    json=payload,
                    timeout=10
                )

                sys.stderr.write(f"  [API RESPONSE] Status: {response.status_code}\n")
                if response.status_code != 200:
                    sys.stderr.write(f"  [API ERROR] {response.text[:500]}\n")
                    break

                data = response.json()
                prospects = data.get('data', [])
                if not prospects:
                    break  # No more results

                all_prospects.extend(prospects)

                # If we have enough results after filtering, we can stop early
                if len(all_prospects) >= limit * 10:  # Get 10x more than needed for filtering
                    break

            prospects = all_prospects

            import sys
            sys.stderr.write(f"  [search_prospects] Retrieved {len(prospects)} prospects from API (across {len(all_prospects)//api_limit + 1} pages)\\n")

            # Get account names BEFORE filtering by query
            account_ids = list(set([p.get('accountId') for p in prospects if p.get('accountId')]))
            account_names = {}
            sys.stderr.write(f"  [search_prospects] Found {len(account_ids)} unique account IDs\\n")

            # Fetch account names in batch
            if account_ids:
                for acc_id in account_ids[:20]:  # Limit to avoid too many requests
                    try:
                        acc_resp = requests.get(
                            f"{api_url}/Accounts/{acc_id}",
                            headers=self.headers,
                            timeout=5
                        )
                        if acc_resp.status_code == 200:
                            response_data = acc_resp.json()
                            # Crono API wraps response in {data: {...}, isSuccess: true, errors: []}
                            acc_data = response_data.get('data', {})
                            acc_name = acc_data.get('name', 'Unknown Account')
                            account_names[acc_id] = acc_name
                    except Exception as e:
                        pass  # Silently skip failed account lookups

            # Add account names to prospects
            for p in prospects:
                p['accountName'] = account_names.get(p.get('accountId'), 'Unknown Account')

            # Filter by query client-side if specified (include account name in search)
            before_filter = len(prospects)
            if query:
                query_lower = query.strip().lower()  # Strip whitespace to avoid false negatives
                prospects = [
                    p for p in prospects
                    if query_lower in (p.get('name') or '').lower() or
                       query_lower in (p.get('email') or '').lower() or
                       query_lower in (p.get('accountName') or '').lower()
                ]
                sys.stderr.write(f"  [search_prospects] Filtered from {before_filter} to {len(prospects)} prospects (query='{query}')\\n")

            return [{
                'id': p.get('objectId'),
                'name': p.get('name', 'No Name'),
                'email': p.get('email'),
                'accountId': p.get('accountId'),
                'accountName': p.get('accountName', 'Unknown Account')
            } for p in prospects]

        except Exception as e:
            print(f"Error searching Crono prospects: {e}")
            return []

    def search_accounts(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for accounts/companies in Crono.

        Args:
            query: Search query (company name)
            limit: Max results

        Returns:
            List of standardized account dicts
        """
        results: List[Dict] = []
        seen_ids = set()

        # Try POST /api/v1/Accounts/search for better name search when query provided
        if query:
            try:
                post_url = "https://ext.crono.one/api/v1/Accounts/search"
                payload = {"name": query}
                resp = requests.post(post_url, headers=self.headers, json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    accounts = data.get('data', [])
                    for acc in accounts:
                        std = self._standardize_account(acc)
                        acc_id = std.get('id')
                        if acc_id and acc_id not in seen_ids:
                            seen_ids.add(acc_id)
                            results.append(std)
                else:
                    print(f"Crono POST search status {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                print(f"Error in Crono POST search: {e}")

        # Fallback/augment with GET search (supports empty query to list recent)
        try:
            params = {'limit': limit}
            if query:
                params['search'] = query

            response = requests.get(
                f"{self.base_url}/Accounts",
                headers=self.headers,
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    accounts = data
                else:
                    accounts = data.get('data', data.get('accounts', []))

                for acc in accounts:
                    std = self._standardize_account(acc)
                    acc_id = std.get('id')
                    if acc_id and acc_id not in seen_ids:
                        seen_ids.add(acc_id)
                        results.append(std)
            else:
                print(f"Crono API returned status {response.status_code}: {response.text[:200]}")

        except Exception as e:
            print(f"Error searching Crono accounts: {e}")

        return results

    def get_account_by_id(self, account_id: str) -> Optional[Dict]:
        """Get account details by ID.

        Args:
            account_id: Crono account objectId

        Returns:
            Standardized account dict or None if not found
        """
        try:
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
            account = response.json()
            return self._standardize_account(account)
        except Exception as e:
            print(f"Error fetching Crono account: {e}")
            return None

    def create_note(self, account_id: str, content: str, title: Optional[str] = None) -> Dict:
        """Create a note on a Crono account.

        Args:
            account_id: Crono account objectId
            content: Note content (supports HTML)
            title: Optional note title (not used by Crono API)

        Returns:
            Dict with 'id' (account_id) and 'created_at' if successful
        """
        try:
            # Crono API v1 format - Data wrapper with AccountId and description
            payload = {
                "Data": {
                    "AccountId": account_id,
                    "description": content
                }
            }

            response = requests.post(
                f"{self.base_url}/Notes",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            if response.status_code in [200, 201]:
                result = response.json()

                if result.get('isSuccess'):
                    note_data = result.get('data', {})
                    print(f"✅ Note created successfully in Crono for account {account_id}")
                    return {
                        'id': account_id,  # Crono doesn't return note ID directly
                        'created_at': datetime.utcnow().isoformat() + 'Z'
                    }
                else:
                    errors = result.get('errors', [])
                    print(f"❌ Crono API returned isSuccess=false: {errors}")
                    raise Exception(f"Crono note creation failed: {errors}")
            else:
                print(f"❌ Crono API returned status {response.status_code}: {response.text[:200]}")
                raise Exception(f"Crono API error: {response.status_code}")

        except Exception as e:
            print(f"Error creating Crono note: {e}")
            raise

    def get_deals(self, account_id: str, limit: int = 100) -> List[Dict]:
        """Get deals/opportunities for a Crono account.

        Args:
            account_id: Crono account objectId
            limit: Max deals to return

        Returns:
            List of standardized deal dicts
        """
        try:
            # Use /api/v1 base URL for search endpoint (different from /v1)
            api_url = "https://ext.crono.one/api/v1"

            payload = {
                "pagination": {
                    "limit": limit,
                    "offset": 0
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
                "accountId": account_id,
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
                return [self._standardize_deal(opp) for opp in opportunities]
            else:
                print(f"Error fetching Crono deals: {response.status_code} - {response.text[:200]}")
                return []

        except Exception as e:
            print(f"Error fetching Crono deals: {e}")
            return []

    def create_task(self, account_id: str, subject: str, description: Optional[str] = None, due_date: Optional[datetime] = None, task_type: str = "call", prospect_id: Optional[str] = None) -> Dict:
        """
        Creates a task in Crono for a specific account.

        Note: Tasks endpoint uses /api/v1 base URL, not /v1

        Args:
            account_id: Crono account ID
            subject: Task title/subject
            description: Task description
            due_date: Due date (defaults to 7 days from now)
            task_type: Type of task - "call", "email", or "todo"
            prospect_id: Optional prospect/contact ID
        """
        # Default due date to 7 days from now if not provided
        if not due_date:
            due_date = datetime.now() + timedelta(days=7)

        # Map task type string to Crono integer enum
        # CronoTaskTodoType is an integer enum
        type_mapping = {
            "email": 0,            # Email
            "call": 1,             # Phone call
            "linkedin": 2,         # LinkedIn message
            "inmail": 3            # InMail message
        }
        type_value = type_mapping.get(task_type.lower(), 1)  # Default to call (1)

        # Format date as RFC 3339 (section 5.6) with Z suffix for UTC
        # Example: 2017-07-21T17:32:28Z
        activity_date_str = due_date.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

        # Crono API expects payload wrapped in "data" object
        payload = {
            "data": {
                "accountId": account_id,
                "prospectId": prospect_id or "",  # Empty string if no contact
                "opportunityId": None,
                "type": type_value,  # INTEGER enum (1=call, 2=email, 3=todo)
                "subtype": None,
                "activityDate": activity_date_str,  # RFC 3339 format with Z
                "templateId": None,
                "automatic": False,  # Manual task creation
                "subject": subject,
                "description": description or ""
            }
        }

        try:
            # Tasks endpoint uses /api/v1, not /v1
            api_url = "https://ext.crono.one/api/v1"

            # Log payload for debugging
            import sys
            sys.stderr.write(f"🔧 Creating task with payload: {json.dumps(payload, indent=2)}\n")

            response = requests.post(
                f"{api_url}/Tasks",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            # Log the full response for debugging
            sys.stderr.write(f"📥 Response status: {response.status_code}\n")
            sys.stderr.write(f"📥 Response body: {response.text[:1000]}\n")
            sys.stderr.flush()

            if response.status_code in [200, 201]:
                result = response.json()
                if result.get('isSuccess'):
                    print(f"✅ Task created successfully in Crono for account {account_id}")
                    return result.get('data', {})
                else:
                    errors = result.get('errors', [])
                    print(f"❌ Crono API returned isSuccess=false: {errors}")
                    raise Exception(f"Crono task creation failed: {errors}")
            else:
                print(f"❌ Crono API returned status {response.status_code}: {response.text[:500]}")
                raise Exception(f"Crono API error {response.status_code}: {response.text[:200]}")

        except Exception as e:
            raise CRMIntegrationError(f"Failed to create task in Crono for account {account_id}: {e}")

    def update_deal_stage(self, deal_id: str, stage: str) -> Dict:
        """
        Update deal/opportunity stage in Crono.
        """
        # Map the stage to Crono-specific stage name
        crono_stage = self.get_stage_mapping().get(stage.lower())
        if not crono_stage:
            raise ValueError(f"Unknown deal stage: {stage}. Supported stages: {list(self.get_stage_mapping().keys())}")

        payload = {
            "data": {
                "stage": crono_stage
            }
        }

        try:
            response = requests.put(
                f"{self.base_url}/Opportunities/{deal_id}",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            if response.status_code in [200, 201]:
                result = response.json()
                if result.get('isSuccess'):
                    print(f"✅ Deal {deal_id} updated to stage {stage}")
                    return result.get('data', {})
                else:
                    errors = result.get('errors', [])
                    print(f"❌ Crono API returned isSuccess=false: {errors}")
                    raise Exception(f"Crono deal update failed: {errors}")
            else:
                print(f"❌ Crono API returned status {response.status_code}: {response.text[:200]}")
                raise Exception(f"Crono API error: {response.status_code}")

        except Exception as e:
            raise CRMIntegrationError(f"Failed to update deal {deal_id} to stage {stage}: {e}")

    def update_deal(self, deal_id: str, amount: Optional[float] = None, stage: Optional[str] = None) -> Dict:
        """
        Update deal/opportunity in Crono (amount and/or stage).

        Args:
            deal_id: Crono opportunity objectId
            amount: New amount value (optional)
            stage: New stage name (optional)

        Returns:
            Updated deal data from Crono API
        """
        payload_data = {}

        if amount is not None:
            payload_data["amount"] = amount

        if stage is not None:
            # Map the stage to Crono-specific stage name
            crono_stage = self.get_stage_mapping().get(stage.lower())
            if not crono_stage:
                raise ValueError(f"Unknown deal stage: {stage}")
            payload_data["stage"] = crono_stage

        if not payload_data:
            raise ValueError("Must provide at least one field to update (amount or stage)")

        payload = {"data": payload_data}

        try:
            api_url = "https://ext.crono.one/api/v1"
            response = requests.put(
                f"{api_url}/Opportunities/{deal_id}",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            if response.status_code in [200, 201]:
                result = response.json()
                if result.get('isSuccess'):
                    print(f"✅ Deal {deal_id} updated successfully")
                    return result.get('data', {})
                else:
                    errors = result.get('errors', [])
                    raise Exception(f"Crono deal update failed: {errors}")
            else:
                raise Exception(f"Crono API error: {response.status_code}")

        except Exception as e:
            raise CRMIntegrationError(f"Failed to update deal {deal_id}: {e}")

    def get_stage_mapping(self) -> Dict[str, str]:
        """Get mapping from standard stages to Crono-specific stage names.

        Returns:
            Dict mapping standard stages to Crono stages
        """
        # ASSUMPTION: Crono uses these standard stage names
        # This mapping should be verified and updated based on actual Crono CRM configuration
        return {
            'lead': 'Lead',
            'qualified': 'Qualified',
            'proposal': 'Proposal',
            'negotiation': 'Negotiation',
            'closed_won': 'Closed Won',
            'closed_lost': 'Closed Lost'
        }

    # ==================== Helper Methods (Crono-specific) ====================

    def find_account_by_domain(self, email_domain: str, company_name: Optional[str] = None) -> Optional[Dict]:
        """Find account by email domain or company name using multi-strategy approach.

        This method maintains backward compatibility with the existing Crono client logic.
        It implements a sophisticated multi-strategy search to maximize chances of finding
        the correct account.

        Args:
            email_domain: Email domain (e.g., "acmecorp.com")
            company_name: Optional company name for fallback searches

        Returns:
            Standardized account dict if found, None otherwise
        """
        # Normalize domain for consistent matching
        normalized_email_domain = email_domain.lower().replace('www.', '')

        # Strategy 0: Check local account mappings first
        mapped_value = self._check_domain_mapping(normalized_email_domain)
        if mapped_value:
            print(f"✅ Found account in local mapping for {normalized_email_domain}: {mapped_value}")

            # Check if it's an objectId (contains underscore) or company name
            if '_' in mapped_value:
                # It's an objectId - fetch the account
                print(f"   Treating as objectId, fetching account...")
                account = self.get_account_by_id(mapped_value)
                if account:
                    return account
                else:
                    print(f"⚠️  Mapped account ID {mapped_value} not found in Crono. Falling back to API search.")
            else:
                # It's a company name - use POST search
                print(f"   Treating as company name, using POST search...")
                account = self._search_accounts_by_name(mapped_value)
                if account:
                    print(f"✅ Found account via POST search: {account.get('name')} ({account.get('id')})")
                    return account
                else:
                    print(f"⚠️  Mapped company name '{mapped_value}' not found in Crono. Falling back to API search.")

        # Strategy 1: Search recent accounts and filter by website domain
        print(f"🔍 Strategy 1: Searching recent 200 accounts by domain {normalized_email_domain}")
        accounts_from_search = self.search_accounts(query='', limit=200)
        domain_matches = self._filter_by_website_domain(accounts_from_search, normalized_email_domain)

        if domain_matches:
            print(f"✅ Strategy 1 matched account by domain: {domain_matches[0].get('name')} ({domain_matches[0].get('id')})")
            return domain_matches[0]

        # Fallback strategies using company_name if provided
        if company_name:
            print(f"🔍 No match from Strategy 1. Trying company name searches for '{company_name}'.")

            # Prepare name variations for robust search
            name_variations = [company_name]
            if company_name.islower() or company_name.isupper():
                name_variations.append(company_name.capitalize())
            else:
                name_variations.append(company_name.lower())
                name_variations.append(company_name.upper())
            name_variations = list(set(name_variations))  # Remove duplicates

            for name_var in name_variations:
                # Strategy 2: Try POST search by company name
                print(f"🔍 Strategy 2: Trying POST search by exact name '{name_var}'")
                account = self._search_accounts_by_name(name_var)
                if account:
                    print(f"✅ Strategy 2 matched account by exact name: {account.get('name')} ({account.get('id')})")
                    return account

            for name_var in name_variations:
                # Strategy 3: Try GET search by company name
                print(f"🔍 Strategy 3: Trying GET search by name '{name_var}' (fallback)")
                accounts_from_query = self.search_accounts(query=name_var, limit=10)

                if accounts_from_query:
                    # First pass: Look for exact matches
                    for acc in accounts_from_query:
                        acc_name = acc.get('name', '').lower()
                        if name_var.lower() == acc_name:
                            print(f"✅ Strategy 3 matched account by exact name: {acc.get('name')} ({acc.get('id')})")
                            return acc

                    # Second pass: Look for substring matches
                    for acc in accounts_from_query:
                        acc_name = acc.get('name', '').lower()
                        if name_var.lower() in acc_name:
                            print(f"⚠️  Strategy 3 matched account by partial name: {acc.get('name')} ({acc.get('id')})")
                            print(f"   WARNING: This is a partial match, may not be accurate!")
                            return acc

                    # Return first result if no exact/substring match
                    if accounts_from_query:
                        print(f"✅ Strategy 3 (fallback) matched account: {accounts_from_query[0].get('name')} ({accounts_from_query[0].get('id')})")
                        return accounts_from_query[0]

        # No match found
        print(f"❌ No Crono account found for domain '{normalized_email_domain}' or company '{company_name}'.")
        return None

    def create_meeting_summary(
        self,
        account_id: str,
        meeting_title: str,
        summary_data: Dict,
        meeting_url: Optional[str] = None
    ) -> Optional[str]:
        """Create a structured meeting summary note in Crono.

        This is a convenience method that maintains backward compatibility
        with the existing application flow.

        Args:
            account_id: Crono account objectId
            meeting_title: Meeting title
            summary_data: Dict with tech_stack, pain_points, impact, next_steps, roadblocks
            meeting_url: Optional Fathom meeting URL

        Returns:
            Note ID (account_id) if successful, None otherwise
        """
        # Build plain text content for note
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

        try:
            result = self.create_note(
                account_id=account_id,
                content=content,
                title=meeting_title
            )
            return result.get('id')
        except Exception as e:
            print(f"Error creating meeting summary: {e}")
            return None

    # ==================== Private Helper Methods ====================

    def _standardize_account(self, crono_account: Dict) -> Dict:
        """Convert Crono account format to standardized format.

        Args:
            crono_account: Raw Crono account dict

        Returns:
            Standardized account dict
        """
        return {
            'id': crono_account.get('objectId') or crono_account.get('id'),
            'name': crono_account.get('name', ''),
            'website': crono_account.get('website') or crono_account.get('Website', ''),
            'crm_type': 'crono',
            # Preserve original fields for backward compatibility
            'objectId': crono_account.get('objectId') or crono_account.get('id'),
            **crono_account  # Include all original fields
        }

    def _standardize_deal(self, crono_deal: Dict) -> Dict:
        """Convert Crono opportunity format to standardized deal format.

        Args:
            crono_deal: Raw Crono opportunity dict

        Returns:
            Standardized deal dict
        """
        return {
            'id': crono_deal.get('objectId') or crono_deal.get('id'),
            'name': crono_deal.get('name', ''),
            'stage': crono_deal.get('stage', ''),
            'amount': crono_deal.get('amount', 0.0),
            'currency': crono_deal.get('currency', 'USD'),
            'close_date': crono_deal.get('closeDate', ''),
            'crm_type': 'crono',
            # Preserve original fields for backward compatibility
            'objectId': crono_deal.get('objectId') or crono_deal.get('id'),
            **crono_deal  # Include all original fields
        }

    def _search_accounts_by_name(self, company_name: str) -> Optional[Dict]:
        """Search for account by exact company name using POST endpoint.

        Args:
            company_name: Company name to search for

        Returns:
            Standardized account dict if found, None otherwise
        """
        try:
            # Use POST /api/v1/Accounts/search with "name" parameter
            payload = {"name": company_name}
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
                    return self._standardize_account(accounts[0])

            return None

        except Exception as e:
            print(f"Error searching accounts by name: {e}")
            return None

    def _check_domain_mapping(self, email_domain: str) -> Optional[str]:
        """Check if email domain has a manually configured account mapping.

        Args:
            email_domain: Email domain to check (normalized)

        Returns:
            Account ID or company name if mapped, None otherwise
        """
        try:
            if os.path.exists(self.account_mappings_file):
                with open(self.account_mappings_file, 'r') as f:
                    mappings = json.load(f)

                domain_map = mappings.get('domain_to_account', {})
                # Normalize domain (lowercase, no www)
                normalized_domain = email_domain.lower().replace('www.', '')

                return domain_map.get(normalized_domain)
        except Exception as e:
            print(f"Warning: Could not read account mappings: {e}")

        return None

    def _filter_by_website_domain(self, accounts: List[Dict], target_domain: str) -> List[Dict]:
        """Filter accounts by comparing website field domain with target domain.

        Args:
            accounts: List of standardized account dicts
            target_domain: Domain to match (e.g., "acmecorp.com")

        Returns:
            Filtered list of accounts with matching website domain
        """
        matching_accounts = []
        target_domain_clean = target_domain.lower().replace('www.', '')

        for account in accounts:
            website = account.get('website', '')

            if not website:
                continue

            try:
                # Parse website URL to extract domain
                if not website.startswith(('http://', 'https://')):
                    website = 'https://' + website

                parsed = urlparse(website)
                website_domain = parsed.netloc.lower().replace('www.', '')

                # Match if domains are the same
                if website_domain == target_domain_clean:
                    matching_accounts.append(account)

            except Exception:
                # If parsing fails, try simple string comparison
                website_clean = website.lower().replace('http://', '').replace('https://', '').replace('www.', '').strip('/')
                if target_domain_clean in website_clean or website_clean in target_domain_clean:
                    matching_accounts.append(account)

        return matching_accounts
