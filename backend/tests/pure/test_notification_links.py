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


# --- the owner may point the link at Frigate instead (#414, second half) ----------------------

from app.services.notification_links import frigate_link, notification_link  # noqa: E402


def test_frigate_link_opens_the_tracked_object_in_explore():
    assert frigate_link("https://frigate.example.com/", "1788874165.969381-ym7r9s") == (
        "https://frigate.example.com/explore?event_id=1788874165.969381-ym7r9s"
    )


def test_frigate_link_without_an_event_opens_explore():
    assert frigate_link("https://frigate.example.com", None) == "https://frigate.example.com/explore"


def test_no_public_frigate_address_means_no_link_not_the_internal_one():
    assert frigate_link("", "abc") is None
    assert frigate_link("   ", "abc") is None


def test_the_target_choice_decides_which_link_a_notification_carries():
    notifications = NotificationSettings(instance_url="https://feeder.example.com", link_target="frigate")
    assert notification_link(notifications, "https://frigate.example.com", "abc") == (
        "https://frigate.example.com/explore?event_id=abc"
    )
    notifications.link_target = "yawamf"
    assert notification_link(notifications, "https://frigate.example.com", "abc") == (
        "https://feeder.example.com/events?event=abc"
    )


def test_frigate_target_with_no_public_address_sends_no_link_at_all():
    notifications = NotificationSettings(instance_url="https://feeder.example.com", link_target="frigate")
    assert notification_link(notifications, "", "abc") is None


# --- an address without a scheme would sink the whole notification, so it counts as none --------

from app.services.notification_links import public_base  # noqa: E402


def test_an_address_without_a_scheme_is_no_address():
    assert public_base("feeder.local:9852") is None
    assert public_base("//feeder.example.com") is None
    assert instance_base(NotificationSettings(instance_url="feeder.local:9852")) is None
    assert frigate_link("frigate.local:8971", "abc") is None


def test_scheme_matching_is_case_insensitive_and_keeps_the_host_as_typed():
    assert public_base(" HTTPS://Feeder.Example.com/ ") == "HTTPS://Feeder.Example.com"
