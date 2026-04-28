"""URL config for sinpapel-drf.

Consumer must include this in their root urls.py:

    urlpatterns = [
        path("sinpapel/api/", include("sinpapel_drf.urls")),
    ]

S13.4: SinpapelRouter() instantiated eager at module import. Django evaluates
urls.py LAZY post-startup, so all apps have completed apps.ready() and
registered their @workflow_enabled models by the time this module loads.
"""
from sinpapel_drf.routers import SinpapelRouter

router = SinpapelRouter()
urlpatterns = router.urls
