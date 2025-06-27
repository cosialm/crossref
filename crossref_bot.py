import re # For parsing reference strings
import requests
from difflib import SequenceMatcher
from urllib.parse import quote_plus

# --- Constants ---
CROSSREF_API_BASE_URL = "https://api.crossref.org/v1"
# TODO: User should ideally configure their actual email for the Mailto parameter.
DEFAULT_MAILTO_EMAIL = "anonymous@example.com" # REPLACE_WITH_YOUR_EMAIL@example.com
# TODO: User might want to update the repository URL if this script is hosted elsewhere.
DEFAULT_USER_AGENT = f"CrossRefBot/1.1 (Python-Requests; mailto:{DEFAULT_MAILTO_EMAIL}; https://github.com/YOUR_USERNAME/YOUR_REPO_NAME/blob/main/crossref_bot.py)"


# --- Helper Functions ---
def _build_api_params(search_params, rows):
    """
    Constructs the dictionary of parameters for the CrossRef API /works endpoint
    based on the structured search_params dictionary.

    Args:
        search_params (dict): A dictionary containing search criteria. Expected keys include:
            "keyword" (str): General keywords for query.bibliographic.
            "title" (str): For query.title.
            "author" (str): For query.author.
            "doi" (str): For query.doi.
            "issn" (str): For filter by ISSN.
            "publication_year_from" (str/int): Start year for from-pub-date filter.
            "publication_year_to" (str/int): End year for until-pub-date filter.
            "affiliation" (str): For query.affiliation.
            "funding_agency_doi" (str): For funder filter (funder's DOI).
            "funding_agency_name" (str): For query against funder name (may use query.bibliographic).
            "publication_type" (str): For type filter (e.g., "journal-article").
            "open_access" (bool): Placeholder for potential OA filter.
            "cited_by_doi" (str): Placeholder for potential citation filter.
            "raw_filters" (list of str): List of pre-formatted filter strings.
        rows (int): Number of results to request from the API.

    Returns:
        dict: A dictionary of parameters suitable for requests.get() targeting the CrossRef API.
    """
    api_request_params = {}
    filters = []

    # General keyword query
    if search_params.get("keyword"):
        # Using query.bibliographic as it's generally recommended for broad keyword/phrase searches
        api_request_params["query.bibliographic"] = search_params["keyword"]

    # Field-specific queries
    if search_params.get("title"):
        api_request_params["query.title"] = search_params["title"]
    if search_params.get("author"):
        api_request_params["query.author"] = search_params["author"]
    # DOI can be a query or a filter. Let's try query first.
    if search_params.get("doi"):
        api_request_params["query.doi"] = search_params["doi"]
    if search_params.get("affiliation"): # query.affiliation might not be a dedicated field, but can be tried
        api_request_params["query.affiliation"] = search_params["affiliation"]
    if search_params.get("funding_agency_name"):
        # This might be better as a general query if not a specific query field.
        # For now, let's assume it contributes to a general query if "keyword" isn't also present.
        if not api_request_params.get("query.bibliographic") and not search_params.get("keyword"):
            api_request_params["query.bibliographic"] = search_params["funding_agency_name"]
        # Alternatively, it might be part of a filter if the API supports it, e.g., funder-name:
        # filters.append(f"funder-name:{quote_plus(search_params['funding_agency_name'])}")


    # Filters
    if search_params.get("issn"):
        filters.append(f"issn:{quote_plus(search_params['issn'])}")

    pub_year_from = search_params.get("publication_year_from")
    pub_year_to = search_params.get("publication_year_to")

    if pub_year_from and pub_year_to:
        filters.append(f"from-pub-date:{pub_year_from}-01-01,until-pub-date:{pub_year_to}-12-31")
    elif pub_year_from:
        filters.append(f"from-pub-date:{pub_year_from}-01-01")
    elif pub_year_to:
        filters.append(f"until-pub-date:{pub_year_to}-12-31")

    if search_params.get("funding_agency_doi"):
        filters.append(f"funder:{quote_plus(search_params['funding_agency_doi'])}")

    if search_params.get("publication_type"):
        filters.append(f"type:{quote_plus(search_params['publication_type'])}")

    # Open Access - This is a placeholder; actual filter needs API doc confirmation
    # Example: if search_params.get("open_access"): filters.append("is-oa:true")
    # Example: if search_params.get("open_access"): filters.append("has-license:true")

    # Cited-by DOI - Placeholder for now, may need special handling
    # if search_params.get("cited_by_doi"):
        # This might not be a simple filter. It could be a parameter like `cited-by=<DOI>`
        # or require a different endpoint. For now, let's assume it could be a filter if supported.
        # filters.append(f"cites:{quote_plus(search_params['cited_by_doi'])}") # Hypothetical

    # Raw filters
    if search_params.get("raw_filters"):
        filters.extend(search_params["raw_filters"])

    if filters:
        api_request_params["filter"] = ",".join(filters)

    api_request_params["rows"] = max(1, min(rows, 1000)) # Ensure rows is between 1 and 1000

    # Add mailto for polite API usage (though it's usually a header)
    # The API docs say "include a mailto parameter with a valid email address"
    # This seems to imply it's a query parameter, not just a header.
    # Let's add it if not already present.
    # if mailto_email and "mailto" not in api_request_params:
    #     api_request_params["mailto"] = mailto_email

    return api_request_params

# --- Core API Interaction Functions ---
def search_crossref_api(search_params, rows=10, mailto_email=None, user_agent=None):
    """
    Performs a search against the CrossRef API's /works endpoint using structured search parameters.

    Args:
        search_params (dict or str): A dictionary containing structured search criteria (see _build_api_params)
                                     OR a simple string for a basic keyword query (for backward compatibility).
        rows (int, optional): Number of results to return. Defaults to 10. Max 1000.
        mailto_email (str, optional): Email address to include in the Mailto parameter and User-Agent string
                                      for polite API usage. Defaults to DEFAULT_MAILTO_EMAIL.
        user_agent (str, optional): Custom User-Agent string. Defaults to DEFAULT_USER_AGENT.

    Returns:
        list: A list of work items (dictionaries) from the CrossRef API response,
              or None if an error occurs or no items are found.
    """
    if not isinstance(search_params, dict):
        # Fallback for old-style simple query string for basic keyword search
        # This maintains backward compatibility for the simple find_and_cite_reference if not updated
        if isinstance(search_params, str):
             search_params = {"keyword": search_params}
        else:
            print("Error: search_params must be a dictionary or a query string.")
            return None

    api_endpoint = f"{CROSSREF_API_BASE_URL}/works"
    api_request_params = _build_api_params(search_params, rows)

    effective_mailto = mailto_email or DEFAULT_MAILTO_EMAIL
    effective_user_agent = user_agent or DEFAULT_USER_AGENT.replace(DEFAULT_MAILTO_EMAIL, effective_mailto)

    headers = {
        "User-Agent": effective_user_agent
    }
    # The "mailto" parameter in query params is also mentioned, let's add it here too if _build_api_params didn't
    if "mailto" not in api_request_params:
        api_request_params["mailto"] = effective_mailto

    try:
        # print(f"Debug: Requesting URL: {api_endpoint}")
        # print(f"Debug: Requesting PARAMS: {api_request_params}")
        # print(f"Debug: Requesting HEADERS: {headers}")
        response = requests.get(api_endpoint, params=api_request_params, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
        return data.get("message", {}).get("items", []) # Safely access items
    except requests.exceptions.RequestException as e:
        print(f"Error during API request to {api_endpoint} with params {api_request_params}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")
        return None
    except ValueError as e: # Includes JSONDecodeError
        print(f"Error decoding JSON response: {e}")
        if 'response' in locals() and response is not None:
            print(f"Response text: {response.text}")
        return None


def get_apa_citation_from_doi(doi, mailto_email=None, user_agent=None):
    """
    Retrieves an APA-formatted citation for a given DOI using CrossRef content negotiation.

    Args:
        doi (str): The DOI (Digital Object Identifier) for which to retrieve the citation.
        mailto_email (str, optional): Email for polite API usage in User-Agent.
        user_agent (str, optional): Custom User-Agent string.

    Returns:
        str: The APA-formatted citation string, or None if an error occurs or citation not found.
    """
    # Crossref API provides content negotiation for citations
    # We can request APA format directly
    url = f"{CROSSREF_API_BASE_URL}/works/{quote_plus(doi)}/transform" # Ensure DOI is URL-encoded

    effective_mailto = mailto_email or DEFAULT_MAILTO_EMAIL
    effective_user_agent = user_agent or DEFAULT_USER_AGENT.replace(DEFAULT_MAILTO_EMAIL, effective_mailto)

    headers = {
        "Accept": "text/x-bibliography; style=apa",
        "User-Agent": effective_user_agent
        # Mailto is typically a query param or part of User-Agent for Crossref,
        # not a separate header for this specific citation endpoint usually.
    }
    try:
        # print(f"Debug: Requesting Citation URL: {url}")
        # print(f"Debug: Requesting Citation HEADERS: {headers}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching APA citation for DOI {doi}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")
        return None

# --- High-Level Search/Utility Functions ---
def find_and_cite_reference(reference_text, expected_title=None, mailto_email=None, user_agent=None):
    """
    Searches for a reference using its text, attempts to parse authors, year, and title
    from the reference_text, then queries CrossRef. Results are scored based on matching
    these parsed fields and the expected_title (if provided).
    Returns an APA citation if a high-confidence match is found.

    Args:
        reference_text (str): The free-text of the reference to search for.
        expected_title (str, optional): The specific title to match against. If not provided,
                                        a title will be parsed from reference_text.
        mailto_email (str, optional): Email for polite API usage.
        user_agent (str, optional): Custom User-Agent string.

    Returns:
        str: An APA-formatted citation if a good match is found, otherwise a message indicating
             the outcome (e.g., no results, low similarity, or error retrieving citation).
    """

    # Step 1: Parse authors, year, and title from reference_text
    parsed_authors = _parse_authors_from_reference(reference_text)
    parsed_year = _parse_year_from_reference(reference_text)

    # Use expected_title if provided, otherwise try to parse title from reference_text
    title_to_match_against = expected_title
    if not title_to_match_against:
        title_to_match_against = _parse_title_from_reference(reference_text, parsed_authors, parsed_year)

    # print(f"Debug Parsed: Authors: {parsed_authors}, Year: {parsed_year}, Title to match: '{title_to_match_against}'")

    # Step 2: Construct search_params for CrossRef API
    search_params = {"keyword": reference_text} # query.bibliographic is a good general starting point

    # Add parsed fields to narrow down the search if they exist
    if parsed_authors:
        search_params["author"] = " ".join(parsed_authors) # Send as a single string; API handles it
    if parsed_year:
        search_params["publication_year_from"] = parsed_year
        search_params["publication_year_to"] = parsed_year
    if title_to_match_against and not expected_title: # If we parsed a title, add it to search query
        search_params["title"] = title_to_match_against
    elif expected_title : # If user provided an expected title, use that for a more specific query title
         search_params["title"] = expected_title


    # print(f"Debug search_params: {search_params}")

    # Using a small number of rows initially, as the top results are most relevant
    results = search_crossref_api(search_params, rows=5, mailto_email=mailto_email, user_agent=user_agent)

    if not results:
        return f"No API results found for query based on: {reference_text[:100]}..."

    best_match_item = None
    highest_overall_score = -1.0

    # Normalize the title to match against (from input)
    normalized_input_title = ""
    if title_to_match_against:
        normalized_input_title = title_to_match_against.lower().strip()
        normalized_input_title = re.sub(r'[^\w\s]', '', normalized_input_title) # Keep only word chars and spaces

    for item in results:
        # --- Title Score ---
        item_title_list = item.get("title")
        current_item_title_str = ""
        if item_title_list and isinstance(item_title_list, list) and item_title_list[0]:
            current_item_title_str = item_title_list[0]

        normalized_item_title = current_item_title_str.lower().strip()
        normalized_item_title = re.sub(r'[^\w\s]', '', normalized_item_title)

        title_score = 0.0
        if normalized_input_title and normalized_item_title: # Ensure both titles are non-empty
             title_score = SequenceMatcher(None, normalized_input_title, normalized_item_title).ratio()

        # --- Author Score ---
        author_score = 0.0
        item_authors_list = item.get("author", [])
        if parsed_authors and item_authors_list:
            item_author_last_names = []
            for author_obj in item_authors_list:
                if isinstance(author_obj, dict) and author_obj.get("family"):
                    item_author_last_names.append(author_obj.get("family").lower())

            match_count = 0
            for pa_norm in [pa.lower() for pa in parsed_authors]:
                if pa_norm in item_author_last_names:
                    match_count += 1
            if parsed_authors: # Avoid division by zero
                author_score = match_count / len(parsed_authors)
        elif not parsed_authors: # If no authors parsed from input, don't penalize/reward based on authors
            author_score = 0.5 # Neutral score if input authors are unknown

        # --- Year Score ---
        year_score = 0.0
        api_year_str = "N/A"
        try:
            # Try to get year from 'published-print', then 'published-online', then 'created'
            year_sources = [
                item.get("published-print", {}).get("date-parts", [[]])[0],
                item.get("published-online", {}).get("date-parts", [[]])[0],
                item.get("created", {}).get("date-parts", [[]])[0]
            ]
            for date_parts in year_sources:
                if date_parts and date_parts[0] is not None: # Check if year part exists
                    api_year_str = str(date_parts[0])
                    break
        except (IndexError, TypeError):
            api_year_str = "N/A"

        if parsed_year and api_year_str == parsed_year:
            year_score = 1.0
        elif not parsed_year: # If no year parsed from input, neutral score
            year_score = 0.5

        # --- Overall Confidence Score ---
        # Weights can be tuned. Title is often most important.
        # If expected_title was provided by user, title_score is more reliable.
        # If title was parsed from ref_string, it's less reliable.
        # --- SCORING WEIGHTS (Tunable Parameters) ---
        title_weight = 0.6 if expected_title else 0.4
        author_weight = 0.3
        year_weight = 0.1 if expected_title else 0.3 # Year becomes more important if title is parsed
        # Ensure weights sum to 1 (or are normalized later if not)
        # Current sum: (0.6+0.3+0.1 = 1.0) or (0.4+0.3+0.3 = 1.0)

        overall_score = (title_weight * title_score) + \
                        (author_weight * author_score) + \
                        (year_weight * year_score)

        # --- Uncomment for detailed scoring debug ---
        # print(f"Debug Item: DOI: {item.get('DOI')}, Title: '{current_item_title_str[:60]}...'")
        # print(f"  Parsed Fields: Authors: {parsed_authors}, Year: {parsed_year}, Input Title: '{title_to_match_against[:60]}'")
        # print(f"  API Fields: Authors: {[a.get('family','N/A') for a in item_authors_list][:3]}, Year: {api_year_str}")
        # print(f"  Scores: Title={title_score:.2f} (w:{title_weight:.1f}), Author={author_score:.2f} (w:{author_weight:.1f}), Year={year_score:.2f} (w:{year_weight:.1f})")
        # print(f"  Overall Score: {overall_score:.2f}\n")
        # --- End Debug ---

        if overall_score > highest_overall_score:
            highest_overall_score = overall_score
            best_match_item = item # Store the whole item
            best_match_item["_calculated_score"] = overall_score # Attach score for later use
            best_match_item["_matched_api_year"] = api_year_str # For debugging

    if best_match_item:
        # print(f"Debug: Best overall candidate DOI: {best_match_item.get('DOI')}, Final Score: {best_match_item['_calculated_score']:.2f}")

        # --- CONFIDENCE THRESHOLD (Tunable Parameter) ---
        # This threshold determines the minimum score for a match to be considered confident.
        CONFIDENCE_THRESHOLD = 0.65

        if best_match_item["_calculated_score"] >= CONFIDENCE_THRESHOLD:
            doi = best_match_item.get("DOI")
            if doi:
                citation = get_apa_citation_from_doi(doi, mailto_email=mailto_email, user_agent=user_agent)
                if citation:
                    api_title = best_match_item.get('title',[""])[0]
                    authors_display = ", ".join([a.get('family', '') for a in best_match_item.get('author', []) if a.get('family')])
                    year_display = best_match_item["_matched_api_year"]

                    # Return only the APA citation string for a confident, successful match
                    return citation
                else:
                    return (f"Status: Matched DOI {doi} (Score: {best_match_item['_calculated_score']:.2f}), "
                            f"but failed to retrieve APA citation. Matched Title: {best_match_item.get('title',[''])[0]}")
            else: # Should not happen if we only consider items with DOI for citation
                 return f"Status: Error - High confidence match (Score: {best_match_item['_calculated_score']:.2f}) found but item has no DOI."
        else:
            api_title = best_match_item.get('title',[""])[0]
            return (f"Status: Low Confidence Match\n"
                    f"Original Reference: {reference_text}\n"
                    f"Input Title for Match: '{title_to_match_against}'\n"
                    f"Highest score was {best_match_item['_calculated_score']:.2f} for title '{api_title}'. This is below the threshold of {CONFIDENCE_THRESHOLD}.")

    return (f"Status: No Confident Match Found\n"
            f"Original Reference: {reference_text}\n"
            f"Input Title for Match: '{title_to_match_against}'")


# --- Helper functions for parsing reference strings ---
def _parse_authors_from_reference(ref_string):
    """
    Rudimentary parsing of author last names from a reference string.
    Focuses on patterns like "Author, A." or "Author1, A. & Author2, B."
    Returns a list of probable last names. This is a simplified parser.
    """
    authors = []
    # Try to find text before a potential year pattern like (YYYY) or a title start
    # This is very heuristic.
    # Look for patterns like "Lastname, F." or "Lastname F."
    # Also "Name1, F., Name2, G., & Name3, H."
    # Or "Name1 F, Name2 G & Name3 H"

    # Simplified: find capitalized words before a year or common title start cues
    # This regex looks for sequences of capitalized words, possibly with initials/et al.
    # Stops if it sees a year in parentheses or a quote indicating a title.
    author_part_match = re.match(r"^(.*?)(?=\s*(?:\(\d{4}\)|\"\w|\'\w|[\w\s]+[.:]\s*\w))", ref_string)
    if author_part_match:
        author_segment = author_part_match.group(1)
        # Split by common delimiters like '&', 'and', ','
        potential_authors = re.split(r'\s*&\s*|\s+and\s+|\s*,\s*(?=[A-Z])', author_segment)
        for pa in potential_authors:
            # Take the first capitalized word as a likely last name
            name_match = re.match(r"([A-Z][a-z'-]+)", pa.strip())
            if name_match:
                authors.append(name_match.group(1))
    return list(set(authors)) # Return unique names

def _parse_year_from_reference(ref_string):
    """
    Parses a 4-digit year, typically enclosed in parentheses.
    Returns the year as a string, or None.
    """
    match = re.search(r'\((\d{4})\)', ref_string)
    if match:
        return match.group(1)
    # Try without parentheses as a fallback
    match = re.search(r'\b(\d{4})\b', ref_string)
    if match:
        # Ensure it's a plausible year (e.g., not a page number)
        year_candidate = match.group(1)
        if 1700 < int(year_candidate) < 2100: # Basic plausibility
             # Check context: avoid matching if it's likely part of a title or series info
            prev_char_index = match.start() - 1
            if prev_char_index >=0 and ref_string[prev_char_index].isdigit(): # e.g. part of an ISBN or page range
                return None
            return year_candidate
    return None

def _parse_title_from_reference(ref_string, authors, year):
    """
    Rudimentary parsing of a title from a reference string,
    assuming authors and year have been identified.
    This is very heuristic.
    """
    temp_ref = ref_string
    # Remove authors part
    # This is tricky because author formats vary wildly.
    # A simple approach: if authors were found, try removing substrings that look like them from the start.
    # This part needs to be much more robust for real-world use.
    # For now, let's try to find the part after the year.

    if year:
        year_match = re.search(r'(\(\s*' + re.escape(year) + r'\s*\)|' + re.escape(year) + r')\.?', temp_ref)
        if year_match:
            temp_ref = temp_ref[year_match.end():].strip()
            # Often the title is the first significant chunk of text after the year.
            # It might end before a journal name, "In:", "Vol.", "pp.", etc.
            title_match = re.match(r'^(.*?)(?=\s+(?:In\s|Vol\.|[A-Z][a-zÀ-ÿ\s]+(?:Journal|Conference|Proceedings|Book|Press|University|Review)|https://doi\.org|doi:|$))', temp_ref)
            if title_match:
                title_candidate = title_match.group(1).strip().rstrip('.:,')
                # Further clean up: if it's enclosed in quotes, remove them.
                if (title_candidate.startswith('"') and title_candidate.endswith('"')) or \
                   (title_candidate.startswith("'") and title_candidate.endswith("'")):
                    title_candidate = title_candidate[1:-1]
                return title_candidate.strip()
    # Fallback: if no year, or title not found after year, this is very hard.
    # Maybe return a large chunk of the latter part of the string.
    # This part is highly experimental and likely to be inaccurate.
    # A better approach would involve more sophisticated NLP or library-based parsing.
    if len(ref_string) > 120: # take last 120 chars if ref string is long and no other cues found
        title_candidate = ref_string[-120:].strip()
        # Attempt to remove trailing journal/page info if it looks like it
        title_candidate = re.sub(r'\.\s+(?:[A-Z][\w\s&]+(?:Journal|Conf|Proc|Rev|Bull)|Vol\.|pp\.|\d+[:\-\(]).*$', '', title_candidate)
        return title_candidate.strip('.:, ')
    return ref_string.strip('.:, ') # as a last resort, the (cleaned) whole string


# --- Functions for Conceptual Backend Support for Alerts/RSS ---
def get_new_works(search_criteria_params, since_datetime_str, date_type="from-index-date", rows=20, mailto_email=None, user_agent=None):
    """
    Retrieves works that are new or updated since a given datetime,
    based on specified search criteria.

    Args:
        search_criteria_params (dict): Standard search parameters for the query.
        since_datetime_str (str): ISO 8601 datetime string (e.g., "2023-01-01T00:00:00Z").
                                    The function will search for items after this date.
        date_type (str): The type of date filter to use. Options:
                         "from-created-date": Matches based on when the DOI was first seen by Crossref.
                         "from-update-date": Matches based on when the DOI was last updated by the publisher.
                         "from-index-date": Matches based on when the DOI was last indexed by Crossref (most comprehensive for "newly available").
        rows (int): Number of results to return.
        mailto_email (str, optional): Email for Mailto header.
        user_agent (str, optional): User-Agent string.

    Returns:
        list: A list of work items, or None if an error occurs.
    """
    if not isinstance(search_criteria_params, dict):
        print("Error: search_criteria_params must be a dictionary.")
        return None
    if date_type not in ["from-created-date", "from-update-date", "from-index-date"]:
        print(f"Error: Invalid date_type '{date_type}'. Must be one of 'from-created-date', 'from-update-date', 'from-index-date'.")
        return None

    # Create a copy to avoid modifying the original params
    params_for_new_works = search_criteria_params.copy()
    
    # Add or update the specific date filter
    # Filters are comma-separated, so we need to handle existing filters carefully
    existing_filters = params_for_new_works.get("filter", "")
    new_date_filter = f"{date_type}:{since_datetime_str}"

    if existing_filters:
        # Check if a similar date filter already exists and replace it, or append
        filters_list = existing_filters.split(',')
        # Remove any existing filters of the chosen date_type or other from/until date types to avoid conflict
        conflicting_date_prefixes = ["from-created-date", "until-created-date",
                                     "from-update-date", "until-update-date",
                                     "from-index-date", "until-index-date",
                                     "from-pub-date", "until-pub-date", # These are less likely but good to be cautious
                                     "from-deposit-date", "until-deposit-date"] # another type

        # Remove any conflicting date filters
        cleaned_filters = [f for f in filters_list if not any(f.startswith(prefix) for prefix in conflicting_date_prefixes)]

        cleaned_filters.append(new_date_filter)
        params_for_new_works["filter"] = ",".join(cleaned_filters)
    else:
        params_for_new_works["filter"] = new_date_filter

    # It's often useful to sort by the date used for polling
    # e.g., sort=indexed&order=asc
    # The `sort` parameter is separate from `filter`
    if "sort" not in params_for_new_works: # Allow user to specify their own sort if needed
        sort_field_map = {
            "from-created-date": "created",
            "from-update-date": "updated",
            "from-index-date": "indexed"
        }
        params_for_new_works["sort"] = sort_field_map[date_type]
        params_for_new_works["order"] = "asc" # Get oldest new items first

    # print(f"Debug: Params for get_new_works: {params_for_new_works}")
    return search_crossref_api(params_for_new_works, rows=rows, mailto_email=mailto_email, user_agent=user_agent)


if __name__ == "__main__":
    # --- Example 1: Original find_and_cite_reference usage (now uses new backend) ---
    print("--- Example 1: Find and Cite Reference ---")
    dummy_reference_text = "The effect of climate change on biodiversity"
    dummy_expected_title = "Climate change and sustainability of biodiversity" # Example, likely won't match perfectly

    # It's good practice to provide a real email if you are using this script frequently
    user_email = "testing@example.com" # Using a testing email

    citation_result = find_and_cite_reference(dummy_reference_text, dummy_expected_title, mailto_email=user_email)
    print(f"Citation Result for '{dummy_expected_title}':\n{citation_result}\n")

    # --- Example 2: Direct APA citation retrieval for a known DOI ---
    print("--- Example 2: Direct APA Citation Retrieval ---")
    known_doi = "10.1007/978-3-319-98681-4_25" # Example DOI
    apa_citation = get_apa_citation_from_doi(known_doi, mailto_email=user_email)
    if apa_citation:
        print(f"APA Citation for {known_doi}:\n{apa_citation}\n")
    else:
        print(f"Failed to get APA citation for {known_doi}\n")

    # --- Example 3: Advanced Search - Author and Year Range ---
    print("--- Example 3: Advanced Search - Author and Year Range ---")
    advanced_params_author_year = {
        "author": "Einstein",
        "publication_year_from": "1905",
        "publication_year_to": "1905",
        # "keyword": "electrodynamics" # optional additional keyword
    }
    results_author_year = search_crossref_api(advanced_params_author_year, rows=3, mailto_email=user_email)
    if results_author_year:
        print(f"Found {len(results_author_year)} results for Einstein 1905:")
        for item in results_author_year:
            title = item.get("title", ["No Title"])[0]
            doi = item.get("DOI", "N/A")
            print(f"  Title: {title}, DOI: {doi}")
    else:
        print("No results for Einstein 1905 search.")
    print("\n")

    # --- Example 4: Advanced Search - Title and Publication Type (Journal Article) ---
    print("--- Example 4: Advanced Search - Title and Publication Type ---")
    advanced_params_title_type = {
        "title": "Applications of machine learning", # Broad title
        "publication_type": "journal-article"
    }
    results_title_type = search_crossref_api(advanced_params_title_type, rows=3, mailto_email=user_email)
    if results_title_type:
        print(f"Found {len(results_title_type)} journal articles for 'Applications of machine learning':")
        for item in results_title_type:
            title = item.get("title", ["No Title"])[0]
            doi = item.get("DOI", "N/A")
            container_title = item.get("container-title", ["N/A"])[0]
            print(f"  Title: {title}\n    Journal: {container_title}, DOI: {doi}")
    else:
        print("No results for title and type search.")
    print("\n")

    # --- Example 5: Advanced Search - ISSN (specific journal) ---
    print("--- Example 5: Advanced Search - ISSN (Specific Journal) ---")
    # Nature's ISSN: 0028-0836 (print), 1476-4687 (online)
    advanced_params_issn = {
        "issn": "0028-0836",
        "publication_year_from": "2023" # Get recent articles
    }
    results_issn = search_crossref_api(advanced_params_issn, rows=2, mailto_email=user_email)
    if results_issn:
        print(f"Found {len(results_issn)} results for ISSN 0028-0836 (from 2023):")
        for item in results_issn:
            title = item.get("title", ["No Title"])[0]
            doi = item.get("DOI", "N/A")
            print(f"  Title: {title}, DOI: {doi}")
    else:
        print("No results for ISSN search.")
    print("\n")

    # --- Example 6: Advanced Search - Funder DOI ---
    # print("--- Example 6: Advanced Search - Funder DOI ---")
    # # Example: National Science Foundation funder DOI "10.13039/100000001"
    # advanced_params_funder = {
    #     "funding_agency_doi": "10.13039/100000001",
    #     "keyword": "artificial intelligence", # Look for AI research funded by NSF
    #     "publication_year_from": "2022"
    # }
    # results_funder = search_crossref_api(advanced_params_funder, rows=2, mailto_email=user_email)
    # if results_funder:
    #     print(f"Found {len(results_funder)} results for NSF-funded AI research (from 2022):")
    #     for item in results_funder:
    #         title = item.get("title", ["No Title"])[0]
    #         doi = item.get("DOI", "N/A")
    #         print(f"  Title: {title}, DOI: {doi}")
    # else:
    #     print("No results for funder search.")
    # print("\n")

    # --- Example 7: Using raw_filters (e.g., for a filter not yet explicitly supported)
    print("--- Example 7: Advanced Search - Using Raw Filters ---")
    # This is a hypothetical example. `has-abstract:true` is a real filter.
    advanced_params_raw_filter = {
        "keyword": "quantum computing",
        "raw_filters": ["has-abstract:true"],
        "publication_year_from": "2023"
    }
    results_raw_filter = search_crossref_api(advanced_params_raw_filter, rows=2, mailto_email=user_email)
    if results_raw_filter:
        print(f"Found {len(results_raw_filter)} results for 'quantum computing' with abstracts (from 2023):")
        for item in results_raw_filter:
            title = item.get("title", ["No Title"])[0]
            doi = item.get("DOI", "N/A")
            # The filter 'has-abstract:true' should ensure the 'abstract' field is present.
            # The content of item.get('abstract') is usually a string (the abstract itself).
            abstract_content = item.get('abstract')
            is_abstract_present_and_non_empty = bool(abstract_content)
            print(f"  Title: {title}, DOI: {doi}, Abstract present: {is_abstract_present_and_non_empty}")
    else:
        print("No results for raw filter search.")
    print("\n")

    # --- Example 8: Get New Works (for Alerts/RSS backend conceptual test) ---
    print("--- Example 8: Get New Works (Alerts/RSS backend) ---")
    # Get a timestamp from a week ago for "since_datetime_str"
    from datetime import datetime, timedelta, timezone # Added timezone
    # Use timezone-aware UTC datetime as per DeprecationWarning for utcnow()
    one_week_ago_dt = datetime.now(timezone.utc) - timedelta(days=7)
    # Format as ISO 8601 string, e.g., "2023-01-01T00:00:00Z"
    # Crossref seems to prefer just date for some from-* filters, but full datetime for others.
    # For from-index-date, from-created-date, from-update-date, full ISO8601 is better.
    since_timestamp_str = one_week_ago_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    alert_search_params = {
        "keyword": "artificial intelligence ethics", # More specific topic for alerts
        "publication_type": "journal-article",
        "raw_filters": ["has-abstract:true"] # Example: only interested in those with abstracts
    }

    print(f"Checking for new journal articles with abstracts on 'artificial intelligence ethics' since {since_timestamp_str} (using from-index-date)...")
    new_works_indexed = get_new_works(alert_search_params, since_timestamp_str, date_type="from-index-date", rows=3, mailto_email=user_email)

    if new_works_indexed is not None: # Check for None (error) vs empty list (no results)
        if new_works_indexed:
            print(f"Found {len(new_works_indexed)} new/updated (by index date) works:")
            for item in new_works_indexed:
                title = item.get("title", ["No Title"])[0]
                doi = item.get("DOI", "N/A")
                indexed_date_parts = item.get("indexed", {}).get("date-parts", [[]])[0]
                indexed_date_str = "-".join(map(str, indexed_date_parts)) if indexed_date_parts else "N/A"
                print(f"  Title: {title}\n    DOI: {doi}, Indexed: {indexed_date_str}")
        else: # Empty list, valid response
            print("No new works found for the criteria and timeframe (indexed date).")
    else: # None, indicates an error from search_crossref_api
        print("Error occurred while fetching new works (indexed date).")
    print("\n")

    # Example with from-created-date (might yield different results) - kept commented for brevity
    # print(f"Checking for new journal articles on 'artificial intelligence ethics' since {since_timestamp_str} (using from-created-date)...")
    # new_works_created = get_new_works(alert_search_params, since_timestamp_str, date_type="from-created-date", rows=3, mailto_email=user_email)
    # if new_works_created is not None:
    #     if new_works_created:
    #         print(f"Found {len(new_works_created)} new (by created date) works:")
    #         for item in new_works_created:
    #             title = item.get("title", ["No Title"])[0]
    #             doi = item.get("DOI", "N/A")
    #             created_date_parts = item.get("created", {}).get("date-parts", [[]])[0]
    #             created_date_str = "-".join(map(str,created_date_parts)) if created_date_parts else "N/A"
    #             print(f"  Title: {title}\n    DOI: {doi}, Created: {created_date_str}")
    #     else:
    #         print("No new works found for the criteria and timeframe (created date).")
    # else:
    #     print("Error occurred while fetching new works (created date).")
    # print("\n")

    # --- Example 9: Test specific problematic reference for accuracy improvement ---
    print("--- Example 9: Accuracy Test for 'Maine & Bell' Reference ---")
    problematic_reference = "Maine, R., & Bell, S. (2024). Financial Dependency and Infrastructure Debt in Small Island Developing States."
    # We don't provide an expected_title here, to rely on the parser and multi-factor matching.
    # If we had an exact expected title from a bibliography, we could provide it.
    accuracy_test_result = find_and_cite_reference(problematic_reference, mailto_email=user_email)
    print(f"Result for problematic reference:\n{accuracy_test_result}\n")

    another_problematic_ref = "Shannon, C. E. (1948). A mathematical theory of communication. Bell System Technical Journal, 27(3), 379-423."
    shannon_expected_title = "A mathematical theory of communication" # Providing expected title
    accuracy_test_result_2 = find_and_cite_reference(another_problematic_ref, expected_title=shannon_expected_title, mailto_email=user_email)
    print(f"Result for Shannon reference (with expected title):\n{accuracy_test_result_2}\n")

    # Test with a known good DOI to see if it can find it
    # Reference for DOI: 10.1038/s41586-021-03317-6 (DeepMind AlphaFold paper)
    alphafold_ref_text = "Jumper, J., et al. (2021). Highly accurate protein structure prediction with AlphaFold. Nature, 596(7873), 583-589."
    alphafold_expected_title = "Highly accurate protein structure prediction with AlphaFold"
    alphafold_result = find_and_cite_reference(alphafold_ref_text, expected_title=alphafold_expected_title, mailto_email=user_email)
    print(f"Result for AlphaFold reference:\n{alphafold_result}\n")

