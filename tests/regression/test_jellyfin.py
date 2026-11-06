"""Synthetic catalogue records and MockTransport, never a real Jellyfin endpoint."""
import httpx
import pytest

from app.adapters import jellyfin

ASYNC_CLIENT = httpx.AsyncClient

ITEM = {"Id": "a" * 32, "Type": "Movie", "Name": "Dune", "ProductionYear": 2021,
        "ProviderIds": {"Tmdb": "438631"}, "LocationType": "FileSystem",
        "MediaSources": [{"Id": "fixture-source"}]}


def payload(*items):
    return {"Items": list(items), "TotalRecordCount": len(items), "StartIndex": 0}


def test_exact_identity_and_year():
    status, movie, choices = jellyfin.resolve(payload(ITEM), "DUNE", 2021)
    assert status == "resolved" and movie.tmdb_id == "438631" and movie.item_id == "a" * 32
    assert not choices
    assert jellyfin.resolve(payload(ITEM), "Dune", 1984)[0] == "not_found"
    assert jellyfin.resolve(payload(ITEM), "Dun")[0] == "not_found"


@pytest.mark.parametrize("title,year,expected,tmdb", [
    ("Top Gun",1986,"not_found",None), ("Top Gun",None,"not_found",None),
    ("Top Gun: Maverick",2022,"resolved","361743"),
    ("Moana",None,"ambiguous",None), ("Moana",2016,"resolved","277834"),
    ("Moana",2026,"resolved","1108427"), ("Moana 2",2024,"resolved","1241982"),
])
def test_observed_catalogue_exactness_and_genuine_ambiguity(title, year, expected, tmdb):
    import json
    from pathlib import Path
    evidence=json.loads((Path(__file__).resolve().parents[1]/"fixtures/jellyfin-movies-20261106.json").read_text())
    # Observed identity metadata; the media-source field is an explicit offline stub.
    items=[{"Id":m["item_id"],"Name":m["title"],"ProductionYear":m["year"],"Type":"Movie",
            "ProviderIds":{"Tmdb":m["tmdb_id"]},"LocationType":"FileSystem","MediaSources":[{"Id":"synthetic-source"}]}
           for m in evidence["movies"]]
    status,movie,choices=jellyfin.resolve(payload(*items),title,year)
    assert status==expected
    assert (movie.tmdb_id if movie else None)==tmdb
    if status=="ambiguous":assert {x["year"] for x in choices}=={2016,2026}


@pytest.mark.asyncio
async def test_title_index_export_is_scoped_complete_and_bounded(monkeypatch,transport):
    monkeypatch.setattr(jellyfin.httpx,"AsyncClient",lambda **kw: ASYNC_CLIENT(transport=httpx.MockTransport(
        lambda r:httpx.Response(200,json=payload(ITEM))),**kw))
    value=await jellyfin.JellyfinClient().title_index()
    assert value=={"schema":1,"user_id":"b"*32,"library_id":"c"*32,"titles":["Dune"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [{"Items":[],"TotalRecordCount":1}, {"Items":[],"TotalRecordCount":0},
    {"Items":[ITEM],"TotalRecordCount":2}, {"Items":[ITEM],"TotalRecordCount":True},
    {"Items":[{**ITEM,"Type":"Series"}],"TotalRecordCount":1}])
async def test_partial_or_wrong_index_export_is_not_published(data,monkeypatch,transport):
    monkeypatch.setattr(jellyfin.httpx,"AsyncClient",lambda **kw: ASYNC_CLIENT(transport=httpx.MockTransport(
        lambda r:httpx.Response(200,json=data)),**kw))
    with pytest.raises(jellyfin.CatalogueUnavailable):await jellyfin.JellyfinClient().title_index()


def test_remakes_duplicates_and_truncation():
    old = {**ITEM, "ProductionYear": 1984, "ProviderIds": {"Tmdb": "841"}}
    assert jellyfin.resolve(payload(ITEM, old), "Dune")[0] == "ambiguous"
    assert jellyfin.resolve(payload(ITEM, old), "Dune", 1984)[1].tmdb_id == "841"
    assert jellyfin.resolve(payload(ITEM, ITEM), "Dune", 2021)[0] == "ambiguous"
    with pytest.raises(jellyfin.CatalogueUnavailable):
        jellyfin.resolve({**payload(ITEM), "TotalRecordCount": 2}, "Dune")
    with pytest.raises(jellyfin.CatalogueUnavailable):
        jellyfin.resolve(payload(*([ITEM] * jellyfin.LIMIT)), "Dune")
    assert jellyfin.resolve(payload(), "Missing")[0] == "not_found"


def test_incomplete_duplicate_is_unavailable_not_genuine_ambiguity():
    with pytest.raises(jellyfin.CatalogueUnavailable):
        jellyfin.resolve(payload(ITEM,{**ITEM,"ProviderIds":{}}),"Dune")


@pytest.mark.parametrize("changes", [
    {"ProviderIds": {}}, {"ProviderIds": {"Tmdb": "https://bad.invalid"}},
    {"ProviderIds": {"Tmdb": 1}}, {"ProviderIds": {"Tmdb": "0"}},
    {"Id": "../../unsafe"}, {"ProductionYear": None}, {"ProductionYear": True},
    {"LocationType": "Virtual"}, {"IsPlaceHolder": True}, {"MediaSources": []},
])
def test_incomplete_or_unavailable_film_rejected(changes):
    with pytest.raises(jellyfin.CatalogueUnavailable):
        jellyfin.resolve(payload({**ITEM, **changes}), "Dune")


@pytest.mark.parametrize("data", [None, {}, {"Items": []}, {"Items": [{}], "TotalRecordCount": 0},
    {"Items": [None], "TotalRecordCount": 1}, {"Items": [], "TotalRecordCount": True}])
def test_malformed_envelopes(data):
    with pytest.raises(jellyfin.CatalogueUnavailable):
        jellyfin.resolve(data, "Dune")


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setenv("JELLYFIN_USER_ID", "b" * 32)
    monkeypatch.setenv("JELLYFIN_MOVIE_LIBRARY_ID", "c" * 32)
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload(ITEM))
    real_client = httpx.AsyncClient
    def factory(**kwargs):
        assert kwargs == {"timeout": 4, "trust_env": False, "follow_redirects": False}
        return real_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(jellyfin.httpx, "AsyncClient", factory)
    return requests


@pytest.mark.asyncio
async def test_authenticated_bounded_movie_library_get(transport):
    result = await jellyfin.JellyfinClient().lookup("Dune", 2021)
    assert result[0] == "resolved"
    request, = transport
    assert request.method == "GET" and request.url.path == "/Items"
    assert request.headers["Authorization"] == 'MediaBrowser Token="isolated-test-placeholder"'
    assert "X-Emby-Token" not in request.headers
    assert "token" not in str(request.url).lower()
    assert request.url.params["ParentId"] == "c" * 32
    assert request.url.params["UserId"] == "b" * 32
    assert request.url.params["IncludeItemTypes"] == "Movie"
    assert request.url.params["Limit"] == str(jellyfin.LIMIT)
    assert request.url.params["Years"] == "2021"


@pytest.mark.asyncio
async def test_file_credential_precedes_environment_and_is_encoded(transport, monkeypatch):
    monkeypatch.setenv("JELLYFIN_TOKEN_FILE", "/isolated-fixture/catalogue.token")
    def read(path, **kwargs):
        assert str(path).replace("\\", "/") == "/isolated-fixture/catalogue.token"
        assert kwargs == {"encoding": "utf-8"}
        return 'fixture"token\\value\n'
    monkeypatch.setattr(jellyfin.Path, "read_text", read)
    assert (await jellyfin.JellyfinClient().lookup("Dune"))[0] == "resolved"
    assert transport[0].headers["Authorization"] == 'MediaBrowser Token="fixture%22token%5Cvalue"'


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "unreadable", "encoding", "empty"])
async def test_file_credential_failure_never_falls_back_or_sends(failure, transport, monkeypatch):
    monkeypatch.setenv("JELLYFIN_TOKEN_FILE", "/isolated-fixture/catalogue.token")
    def read(path, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("private-credential-path")
        if failure == "unreadable":
            raise PermissionError("private-credential-path")
        if failure == "encoding":
            raise UnicodeError("private-credential-value")
        return " \n"
    monkeypatch.setattr(jellyfin.Path, "read_text", read)
    with pytest.raises(jellyfin.CatalogueUnavailable) as exc:
        await jellyfin.JellyfinClient().lookup("Dune")
    assert not str(exc.value) and not transport


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://jellyfin.invalid", "https://user:password@jellyfin.invalid",
    "https://jellyfin.invalid?api_key=bad", "file:///tmp/catalogue", "https://jellyfin.invalid/#bad"])
async def test_unsafe_config_never_sends_request(url, transport, monkeypatch):
    monkeypatch.setenv("JELLYFIN_URL", url)
    with pytest.raises(jellyfin.CatalogueUnavailable):
        await jellyfin.JellyfinClient().lookup("Dune")
    assert not transport


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["auth", "redirect", "json", "oversize", "timeout"])
async def test_http_failures_are_sanitised(failure, monkeypatch, transport):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private-token-upstream-body", request=request)
        if failure == "auth":
            return httpx.Response(401, text="private-token-upstream-body")
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://other.invalid"})
        if failure == "json":
            return httpx.Response(200, text="private-token-upstream-body")
        return httpx.Response(200, content=b"x" * (jellyfin.MAX_BYTES + 1))
    monkeypatch.setattr(jellyfin.httpx, "AsyncClient", lambda **kw: ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(jellyfin.CatalogueUnavailable) as exc:
        await jellyfin.JellyfinClient().lookup("Dune")
    assert "private-token" not in str(exc.value)
