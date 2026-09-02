"use client";

import {useEffect, useState} from "react";
import Link from "next/link";

import {apiClient, ApiClientError} from "../../lib/api/client";
import type {SavedCharacterSummary} from "../../lib/api/types";

export function SavedCharactersWorkspace() {
  const [characters, setCharacters] = useState<SavedCharacterSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiClientError | null>(null);

  useEffect(() => {
    let active = true;
    apiClient.listSavedCharacters().then(
      (response) => {
        if (active) {
          setCharacters(response.characters);
          setLoading(false);
        }
      },
      (caught) => {
        if (active) {
          setError(caught instanceof ApiClientError ? caught : null);
          setLoading(false);
        }
      },
    );
    return () => { active = false; };
  }, []);

  return (
    <main className="reference-shell saved-shell">
      <header className="reference-header">
        <div>
          <p className="workspace-kicker">Workspace</p>
          <h1 className="workspace-title">Saved Characters</h1>
          <p className="column-subtitle">Open an explicitly saved Character workspace and continue editing.</p>
        </div>
        <Link className="button-primary" href="/studio">New Character</Link>
      </header>
      {loading && <div className="loading">Loading saved Characters...</div>}
      {error && <div className="notice" role="alert"><strong>Unable to load saved Characters</strong><p>{error.message}</p><span className="notice-meta">{error.payload.error.code}</span></div>}
      {!loading && !error && characters.length === 0 && (
        <div className="empty-state"><div><strong>No saved Characters yet.</strong><span>Generate a Character in Studio, then choose Save Character.</span></div></div>
      )}
      <div className="saved-character-grid">
        {characters.map((character) => (
          <article className="field-card saved-character-card" key={character.character_id}>
            <div className="reference-card-top"><span className="reference-game">{character.revision_kind}</span><span className="status-chip passed">{character.skill_count} skills</span></div>
            <h2>{character.display_name}</h2>
            <p className="reference-id">{character.character_id}</p>
            <div className="readonly-grid saved-character-meta">
              <p><strong>Revision</strong>{character.current_revision_id}</p>
              <p><strong>Updated</strong>{new Date(character.updated_at).toLocaleString()}</p>
            </div>
            <Link className="button-secondary" href={`/studio?character=${encodeURIComponent(character.character_id)}`}>Open</Link>
          </article>
        ))}
      </div>
    </main>
  );
}
