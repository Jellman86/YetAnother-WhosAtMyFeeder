import io

import httpx
import pytest
from PIL import Image

from app.auth import create_access_token
from app.config import settings
from app.main import app
from app.services import avatar_service

OWNER = {"Authorization": f"Bearer {create_access_token('owner')}"}


def _jpeg(width: int, height: int, *, gps: bool = False, orientation: int | None = None) -> bytes:
    image = Image.new("RGB", (width, height), (40, 120, 200))
    # A marker in the top-left corner, so orientation and cropping can be checked.
    image.paste((250, 20, 20), (0, 0, width // 4, height // 4))
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {2: (51.0, 30.0, 0.0), 4: (0.0, 7.0, 0.0)}
    if orientation:
        exif[0x0112] = orientation
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


def test_an_upload_becomes_a_small_square_jpeg_without_its_metadata():
    stored = avatar_service.render_avatar(_jpeg(1200, 800, gps=True))
    with Image.open(io.BytesIO(stored)) as image:
        assert image.format == "JPEG"
        assert image.size == (avatar_service.AVATAR_SIZE, avatar_service.AVATAR_SIZE)
        # Re-encoded from pixels: no EXIF, so no location travels with the picture.
        assert not image.getexif()


def test_a_rotated_phone_photo_is_stored_upright():
    # Orientation 6: the camera held sideways; the stored square must be turned to match.
    stored = avatar_service.render_avatar(_jpeg(400, 400, orientation=6))
    with Image.open(io.BytesIO(stored)) as image:
        top_right = image.getpixel((avatar_service.AVATAR_SIZE - 10, 10))
    assert top_right[0] > 200 and top_right[2] < 80


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"", "empty"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "not_an_image"),
        (b"\xff\xd8\xff" + b"0" * 64, "not_an_image"),
        (b"x" * (avatar_service.AVATAR_MAX_UPLOAD_BYTES + 1), "too_large"),
    ],
    ids=["empty", "svg", "truncated_jpeg", "oversized"],
)
def test_anything_that_is_not_a_usable_image_is_refused(data, reason):
    with pytest.raises(avatar_service.AvatarError, match=reason):
        avatar_service.render_avatar(data)


@pytest.fixture
def avatar_path(tmp_path, monkeypatch):
    path = tmp_path / "profile" / "avatar.jpg"
    monkeypatch.setattr(avatar_service, "AVATAR_PATH", path)
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    monkeypatch.setattr(settings.auth, "username", "owner")
    monkeypatch.setattr(settings.public_access, "enabled", True)
    return path


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture")


@pytest.mark.asyncio
async def test_the_owner_can_set_read_and_remove_their_picture(avatar_path):
    async with await _client() as client:
        assert (await client.get("/api/auth/avatar", headers=OWNER)).status_code == 404
        put = await client.put(
            "/api/auth/avatar", headers=OWNER, files={"image": ("me.jpg", _jpeg(640, 480), "image/jpeg")}
        )
        assert put.status_code == 200, put.text
        version = put.json()["avatar_version"]
        assert isinstance(version, int)
        status = (await client.get("/api/auth/status", headers=OWNER)).json()
        assert status["avatar_version"] == version
        got = await client.get("/api/auth/avatar", headers=OWNER)
        assert got.status_code == 200
        assert got.headers["content-type"] == "image/jpeg"
        assert got.content == avatar_path.read_bytes()
        removed = await client.delete("/api/auth/avatar", headers=OWNER)
        assert removed.json() == {"avatar_version": None}
        assert not avatar_path.exists()
        assert (await client.get("/api/auth/status", headers=OWNER)).json()["avatar_version"] is None


@pytest.mark.asyncio
async def test_a_guest_can_neither_see_nor_change_the_picture(avatar_path):
    avatar_path.parent.mkdir(parents=True)
    avatar_path.write_bytes(avatar_service.render_avatar(_jpeg(300, 300)))
    async with await _client() as client:
        assert (await client.get("/api/auth/avatar")).status_code in {401, 403}
        put = await client.put("/api/auth/avatar", files={"image": ("x.jpg", _jpeg(10, 10), "image/jpeg")})
        assert put.status_code in {401, 403}
        assert (await client.delete("/api/auth/avatar")).status_code in {401, 403}
        assert (await client.get("/api/auth/status")).json()["avatar_version"] is None
    assert avatar_path.exists()


@pytest.mark.asyncio
async def test_a_bad_upload_is_refused_and_keeps_the_current_picture(avatar_path):
    async with await _client() as client:
        await client.put("/api/auth/avatar", headers=OWNER, files={"image": ("a.jpg", _jpeg(300, 300), "image/jpeg")})
        before = avatar_path.read_bytes()
        bad = await client.put(
            "/api/auth/avatar", headers=OWNER, files={"image": ("b.png", b"not an image", "image/png")}
        )
        assert bad.status_code == 400
        assert avatar_path.read_bytes() == before
