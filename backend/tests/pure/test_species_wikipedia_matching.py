from app.routers import species as species_router


def test_ru_bird_article_with_generic_description_is_accepted():
    data = {
        "title": "Большая синица",
        "description": "вид рода синицы",
        "extract": "Большая синица — птица из семейства синицевых, отряда воробьинообразных.",
    }

    assert species_router._bird_relevance_score(data) >= 2
    assert species_router._is_bird_article(data) is True


def test_candidate_scoring_prefers_exact_ru_species_title():
    requested_name = "Большая синица"
    great_tit = {
        "title": "Большая синица",
        "description": "вид рода синицы",
        "extract": "Птица из семейства синицевых (Paridae), отряд воробьинообразных.",
    }
    bukhara_tit = {
        "title": "Бухарская синица",
        "description": "",
        "extract": "Вид птиц из семейства синицевых (Paridae).",
    }

    great_score = species_router._score_wikipedia_candidate(
        great_tit,
        requested_name=requested_name,
        expected_scientific_name="Parus major",
    )
    bukhara_score = species_router._score_wikipedia_candidate(
        bukhara_tit,
        requested_name=requested_name,
        expected_scientific_name="Parus major",
    )

    assert great_score > bukhara_score


def test_short_ascii_terms_use_word_boundaries():
    # "ave" should not be treated as a bird signal inside unrelated words like "average".
    assert species_router._contains_lookup_term("average values only", "ave") is False
    assert species_router._contains_lookup_term("especie de ave", "ave") is True


def test_inaturalist_candidate_scoring_rejects_non_birds_without_scientific_hint():
    taxon = {
        "id": 123,
        "name": "Robinia pseudoacacia",
        "preferred_common_name": "black locust",
        "matched_term": "Robin",
        "iconic_taxon_name": "Plantae",
        "rank": "species",
        "is_active": True,
    }
    score = species_router._score_inaturalist_candidate(taxon, requested_name="Robin")
    assert score == 0


def test_inaturalist_candidate_scoring_prefers_expected_scientific_name():
    matching = {
        "id": 1,
        "name": "Turdus merula",
        "preferred_common_name": "Blackbird",
        "matched_term": "Eurasian Blackbird",
        "iconic_taxon_name": "Aves",
        "rank": "species",
        "is_active": True,
    }
    wrong = {
        "id": 2,
        "name": "Turdus migratorius",
        "preferred_common_name": "American Robin",
        "matched_term": "Blackbird",
        "iconic_taxon_name": "Aves",
        "rank": "species",
        "is_active": True,
    }
    matching_score = species_router._score_inaturalist_candidate(
        matching,
        requested_name="Eurasian Blackbird",
        expected_scientific_name="Turdus merula",
    )
    wrong_score = species_router._score_inaturalist_candidate(
        wrong,
        requested_name="Eurasian Blackbird",
        expected_scientific_name="Turdus merula",
    )
    assert matching_score > wrong_score


def test_select_inaturalist_candidate_prefers_bird_taxon_with_best_match():
    candidates = [
        {
            "id": 30,
            "name": "Robinia pseudoacacia",
            "preferred_common_name": "black locust",
            "matched_term": "Robin",
            "iconic_taxon_name": "Plantae",
            "rank": "species",
            "is_active": True,
        },
        {
            "id": 40,
            "name": "Erithacus rubecula",
            "preferred_common_name": "European Robin",
            "matched_term": "Robin",
            "iconic_taxon_name": "Aves",
            "rank": "species",
            "is_active": True,
        },
    ]
    selected, score = species_router._select_inaturalist_candidate(candidates, requested_name="Robin")
    assert selected is not None
    assert selected.get("id") == 40
    assert score > 0
