"""A notification links back to the detection it announces (#414)."""

from app.config_models import NotificationSettings
from app.services.notification_links import detection_link, instance_base


def test_no_address_means_no_link():
    notifications = NotificationSettings()
    assert instance_base(notifications) is None
    assert detection_link(None, "1788874165.969381-ym7r9s") is None


def test_the_address_is_normalised_before_use():
    notifications = NotificationSettings(instance_url="  https://feeder.example.com/  ")
    assert instance_base(notifications) == "https://feeder.example.com"


def test_the_link_opens_that_detection_on_the_events_page():
    link = detection_link("https://feeder.example.com", "1788874165.969381-ym7r9s")
    assert link == "https://feeder.example.com/events?event=1788874165.969381-ym7r9s"


def test_event_ids_are_url_escaped():
    assert detection_link("https://feeder.example.com", "odd id/&x") == (
        "https://feeder.example.com/events?event=odd%20id%2F%26x"
    )


def test_without_an_event_the_link_opens_the_detections_page():
    assert detection_link("https://feeder.example.com", None) == "https://feeder.example.com/events"


def test_the_older_email_dashboard_address_still_counts():
    notifications = NotificationSettings()
    notifications.email.dashboard_url = "https://feeder.example.com/"
    assert instance_base(notifications) == "https://feeder.example.com"


def test_the_shared_address_wins_over_the_email_one():
    notifications = NotificationSettings(instance_url="https://new.example.com")
    notifications.email.dashboard_url = "https://old.example.com"
    assert instance_base(notifications) == "https://new.example.com"
