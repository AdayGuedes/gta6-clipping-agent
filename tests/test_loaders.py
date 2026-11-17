import json

import pytest

from src.loaders import ErrorDeCarga, cargar_chat, cargar_transcripcion
from src.models import ChatEvent, Segment


def escribir(tmp_path, nombre, contenido):
    ruta = tmp_path / nombre
    if isinstance(contenido, str):
        ruta.write_text(contenido, encoding="utf-8")
    else:
        ruta.write_text(json.dumps(contenido), encoding="utf-8")
    return ruta


def test_transcripcion_json_con_tiempos_en_segundos(tmp_path):
    ruta = escribir(tmp_path, "t.json", [{"start_s": 0, "end_s": 4.5, "text": "hola"}])
    assert cargar_transcripcion(ruta) == [Segment(start_s=0, end_s=4.5, text="hola")]


def test_transcripcion_json_con_tiempos_hhmmss(tmp_path):
    ruta = escribir(
        tmp_path,
        "t.json",
        [{"start_s": "00:01:05", "end_s": "00:01:10", "text": "ey"}],
    )
    assert cargar_transcripcion(ruta) == [Segment(start_s=65, end_s=70, text="ey")]


def test_transcripcion_json_mezcla_ambos_formatos_en_el_mismo_fichero(tmp_path):
    ruta = escribir(
        tmp_path,
        "t.json",
        [
            {"start_s": 5, "end_s": "00:00:09", "text": "uno"},
            {"start_s": "00:00:09", "end_s": 12.5, "text": "dos"},
        ],
    )
    segmentos = cargar_transcripcion(ruta)
    assert [(s.start_s, s.end_s) for s in segmentos] == [(5.0, 9.0), (9.0, 12.5)]


def test_transcripcion_csv(tmp_path):
    ruta = escribir(
        tmp_path,
        "t.csv",
        'start_s,end_s,text\n0,4.5,hola\n00:00:05,00:00:09,"qué, tal"\n',
    )
    assert cargar_transcripcion(ruta) == [
        Segment(start_s=0, end_s=4.5, text="hola"),
        Segment(start_s=5, end_s=9, text="qué, tal"),
    ]


def test_chat_json(tmp_path):
    ruta = escribir(tmp_path, "c.json", [{"t_s": 3725, "message": "jajaja"}])
    assert cargar_chat(ruta) == [ChatEvent(t_s=3725, message="jajaja")]


def test_chat_json_con_tiempo_hhmmss(tmp_path):
    ruta = escribir(tmp_path, "c.json", [{"t_s": "01:02:05", "message": "jajaja"}])
    assert cargar_chat(ruta)[0].t_s == 3725.0


def test_chat_csv(tmp_path):
    ruta = escribir(tmp_path, "c.csv", "t_s,message\n3725,jajaja\n01:02:06,LUL\n")
    assert cargar_chat(ruta) == [
        ChatEvent(t_s=3725, message="jajaja"),
        ChatEvent(t_s=3726, message="LUL"),
    ]


def test_extension_en_mayusculas(tmp_path):
    ruta = escribir(tmp_path, "C.JSON", [{"t_s": 1, "message": "x"}])
    assert len(cargar_chat(ruta)) == 1


def test_acepta_ruta_como_texto(tmp_path):
    ruta = escribir(tmp_path, "c.json", [{"t_s": 1, "message": "x"}])
    assert len(cargar_chat(str(ruta))) == 1


def test_lista_vacia_devuelve_lista_vacia(tmp_path):
    assert cargar_chat(escribir(tmp_path, "c.json", [])) == []
    assert cargar_chat(escribir(tmp_path, "c.csv", "t_s,message\n")) == []


def test_csv_con_bom_de_excel(tmp_path):
    ruta = tmp_path / "c.csv"
    ruta.write_bytes("﻿t_s,message\n1,hola\n".encode())
    assert cargar_chat(ruta) == [ChatEvent(t_s=1, message="hola")]


def test_claves_extra_se_ignoran_si_estan_las_esperadas(tmp_path):
    ruta = escribir(tmp_path, "c.json", [{"t_s": 1, "message": "x", "user": "ana"}])
    assert cargar_chat(ruta) == [ChatEvent(t_s=1, message="x")]


def test_claves_equivocadas_dicen_que_se_esperaba(tmp_path):
    ruta = escribir(tmp_path, "t.json", [{"inicio": 0, "fin": 4, "texto": "hola"}])
    with pytest.raises(ErrorDeCarga) as error:
        cargar_transcripcion(ruta)
    mensaje = str(error.value)
    assert "t.json" in mensaje
    assert "registro 1" in mensaje
    for clave in ("start_s", "end_s", "text"):
        assert clave in mensaje
    assert "inicio" in mensaje


def test_claves_equivocadas_en_csv_de_chat(tmp_path):
    ruta = escribir(tmp_path, "c.csv", "time,msg\n1,hola\n")
    with pytest.raises(ErrorDeCarga, match="t_s, message"):
        cargar_chat(ruta)


def test_falta_una_sola_clave(tmp_path):
    ruta = escribir(tmp_path, "c.json", [{"t_s": 1}])
    with pytest.raises(ErrorDeCarga, match="faltan las claves message"):
        cargar_chat(ruta)


def test_el_error_indica_el_numero_de_registro(tmp_path):
    ruta = escribir(
        tmp_path,
        "c.json",
        [{"t_s": 1, "message": "a"}, {"t_s": 2, "message": "b"}, {"t_s": 3}],
    )
    with pytest.raises(ErrorDeCarga, match="registro 3"):
        cargar_chat(ruta)


@pytest.mark.parametrize("tiempo", ["0:05:30", "abc", -5, True, None, "99:99:99"])
def test_tiempo_invalido_nombra_fichero_registro_y_clave(tmp_path, tiempo):
    ruta = escribir(tmp_path, "c.json", [{"t_s": tiempo, "message": "x"}])
    with pytest.raises(ErrorDeCarga, match=r"c\.json, registro 1, clave t_s"):
        cargar_chat(ruta)


def test_segmento_con_fin_antes_del_inicio(tmp_path):
    ruta = escribir(tmp_path, "t.json", [{"start_s": 9, "end_s": 4, "text": "x"}])
    with pytest.raises(ErrorDeCarga, match="registro 1.*end_s"):
        cargar_transcripcion(ruta)


def test_texto_que_no_es_cadena(tmp_path):
    ruta = escribir(tmp_path, "c.json", [{"t_s": 1, "message": 42}])
    with pytest.raises(ErrorDeCarga, match="registro 1.*message"):
        cargar_chat(ruta)


def test_json_que_no_es_lista(tmp_path):
    ruta = escribir(tmp_path, "c.json", {"t_s": 1, "message": "x"})
    with pytest.raises(ErrorDeCarga, match="lista de objetos"):
        cargar_chat(ruta)


def test_json_con_elementos_que_no_son_objetos(tmp_path):
    ruta = escribir(tmp_path, "c.json", [{"t_s": 1, "message": "x"}, 5])
    with pytest.raises(ErrorDeCarga, match="registro 2.*objeto"):
        cargar_chat(ruta)


def test_json_mal_formado(tmp_path):
    ruta = escribir(tmp_path, "c.json", "[{")
    with pytest.raises(ErrorDeCarga, match="JSON no válido"):
        cargar_chat(ruta)


def test_csv_sin_cabecera(tmp_path):
    ruta = escribir(tmp_path, "c.csv", "")
    with pytest.raises(ErrorDeCarga, match="cabecera"):
        cargar_chat(ruta)


def test_csv_con_mas_columnas_que_la_cabecera(tmp_path):
    ruta = escribir(tmp_path, "c.csv", "t_s,message\n1,hola,sobra\n")
    with pytest.raises(ErrorDeCarga, match="registro 1.*columnas"):
        cargar_chat(ruta)


def test_csv_con_menos_columnas_que_la_cabecera(tmp_path):
    ruta = escribir(tmp_path, "c.csv", "t_s,message\n1\n")
    with pytest.raises(ErrorDeCarga, match="registro 1"):
        cargar_chat(ruta)


def test_extension_no_soportada(tmp_path):
    ruta = escribir(tmp_path, "c.txt", "t_s,message\n1,x\n")
    with pytest.raises(ErrorDeCarga, match=r"\.json o \.csv"):
        cargar_chat(ruta)


def test_fichero_inexistente(tmp_path):
    with pytest.raises(ErrorDeCarga, match="no existe"):
        cargar_chat(tmp_path / "nada.json")


def test_error_de_carga_es_value_error():
    assert issubclass(ErrorDeCarga, ValueError)
