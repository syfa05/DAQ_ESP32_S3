import json
import sqlite3

from brikia.migrate import upgrade


def test_phase1_projects_are_marked_as_simulated_by_the_migration(settings):
    upgrade(settings, "0003")
    con = sqlite3.connect(settings.db_path)
    con.execute("INSERT INTO projects (nom, ville, architecte, status, created_at) "
                "VALUES ('Ancien', '', '', 'a_valider', '2026-01-01 00:00:00')")
    con.execute("INSERT INTO projects (nom, ville, architecte, status, created_at) "
                "VALUES ('Neuf', '', '', 'a_analyser', '2026-01-01 00:00:00')")
    con.commit(); con.close()

    upgrade(settings)  # -> head (0004)
    con = sqlite3.connect(settings.db_path)
    rows = {r[0]: r[1:] for r in con.execute("SELECT nom, analysis_source, analysis_notes FROM projects")}
    con.close()
    assert rows["Ancien"][0] == "simulated"
    assert "SIMULÉE" in json.loads(rows["Ancien"][1])[0]
    assert rows["Neuf"] == (None, None)  # pas encore analysé : rien à qualifier
