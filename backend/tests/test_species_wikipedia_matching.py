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
