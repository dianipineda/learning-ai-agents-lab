from agent_harness.harness.window import recortar_historial, validar_historial


def t(rol, c):
    return {"role": rol, "content": c}


def uso(*ids):
    return {"role": "assistant", "content": [{"type": "tool_use", "id": i, "name": "x", "input": {}} for i in ids]}


def res(*ids):
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "content": "ok"} for i in ids]}


H = [t("user", "hola"), t("assistant", "hi"),
     t("user", "pedido"), uso("a1"), res("a1"), uso("a2"), res("a2"), t("assistant", "va"),
     t("user", "gracias"), t("assistant", "ok"),
     t("user", "pago"), uso("b1", "b2"), res("b1", "b2"), t("assistant", "pagado")]


def test_historial_de_prueba_es_valido():
    assert validar_historial(H)


def test_tamanos_exactos():
    for maximo, esperado in [(100, 14), (12, 12), (6, 6), (5, 4), (3, 4), (1, 4)]:
        assert len(recortar_historial(H, maximo)) == esperado


def test_toda_ventana_es_valida_y_sufijo_sin_mutar():
    copia = [dict(m) for m in H]
    for n in range(1, 20):
        v = recortar_historial(H, n)
        assert validar_historial(v)
        assert H[len(H) - len(v):] == v
    assert H == copia


def test_el_corte_ingenuo_si_rompe():
    assert any(not validar_historial(H[-n:]) for n in range(1, len(H)))
