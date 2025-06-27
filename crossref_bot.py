import requests
from difflib import SequenceMatcher

def search_crossref_api(query):
    base_url = "https://api.crossref.org/works"
    params = {
        "query": query,
        "rows": 5  # Limit to 5 results for initial testing
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
        return data["message"]["items"]
    except requests.exceptions.RequestException as e:
        print(f"Error during API request: {e}")
        return None

def get_apa_citation_from_doi(doi):
    # Crossref API provides content negotiation for citations
    # We can request APA format directly
    url = f"https://api.crossref.org/works/{doi}/transform"
    headers = {
        "Accept": "text/x-bibliography; style=apa"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching APA citation for DOI {doi}: {e}")
        return None

def find_and_cite_reference(reference_text, expected_title):
    results = search_crossref_api(reference_text)
    if not results:
        return "No results found for your query."

    for item in results:
        title = item.get("title", ["No Title"])[0]
        similarity = SequenceMatcher(None, expected_title.lower(), title.lower()).ratio()

        if similarity >= 0.90:
            doi = item.get("DOI")
            if doi:
                citation = get_apa_citation_from_doi(doi)
                if citation:
                    return citation
                else:
                    return f"Found matching title, but failed to retrieve APA citation for DOI: {doi}"
            else:
                return f"Found matching title \'{title}\' but no DOI available to fetch citation."
    
    return "No matching title found with 90% similarity."

if __name__ == "__main__":
    # Example usage
    dummy_reference = "The effect of climate change on biodiversity"
    dummy_expected_title = "Climate change and sustainability of biodiversity"
    
    citation = find_and_cite_reference(dummy_reference, dummy_expected_title)
    print(f"Result: {citation}")

    # Another example with a known DOI to test citation retrieval directly
    # print("\nTesting direct APA citation retrieval for a known DOI:")
    # known_doi = "10.1007/978-3-319-98681-4_25"
    # apa_citation = get_apa_citation_from_doi(known_doi)
    # if apa_citation:
    #     print(f"APA Citation for {known_doi}:\n{apa_citation}")
    # else:
    #     print(f"Failed to get APA citation for {known_doi}")


