from api.main import por_candidato


def test_por_candidato_maps_lines_to_ids():
    txt = "**cv-07**: sabe SQL y Airflow.\nCV-12 - le falta inglés.\ncv-99: no está en el top.\nlínea suelta"
    assert por_candidato(txt, ["cv-07", "cv-12"]) == {"cv-07": "sabe SQL y Airflow.", "cv-12": "le falta inglés."}
