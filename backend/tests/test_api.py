from core.vlm_client import index_settled_frame
from main import QueryRequest, query_memory


def _post_query(payload):
    """Execute the await-free FastAPI route body without an event loop.

    The Windows sandbox cannot create the Proactor event loop that HTTP test
    clients require. The route is intentionally synchronous internally, so
    advancing its coroutine once verifies the same service wiring.
    """
    coroutine = query_memory(QueryRequest(**payload))
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("query route unexpectedly yielded control")


def test_query_endpoint_returns_verified_result(isolated_env):
    index_settled_frame(
        "desk-01",
        1.0,
        "frames/frame-1.jpg",
        "desk_frame_01.jpg",
        [10, 20, 600, 400],
    )

    response = _post_query({"query": "keys"})

    assert response.state == "FOUND_NOW"
    assert response.bbox == [50.0, 220.0, 100.0, 260.0]
    assert response.frame_id


def test_query_endpoint_handles_empty_query(isolated_env):
    response = _post_query({"query": "  "})

    assert response.state == "UNSURE"
