import assert from "node:assert/strict";
import test from "node:test";

import {ApiClientError, apiClient} from "../lib/api/client";

const summary = {
  schema_version: "web-reference-character-summary/0.1",
  reference_id: "zenless-zone-zero:jane-doe",
  display_name: "Jane Doe",
  localized_names: {"zh-CN": "简·杜"},
  game_id: "zenless-zone-zero",
  game_name: "Zenless Zone Zero",
  native_character_id: "jane-doe",
  faction: "Public Security",
  occupation: null,
  combat_roles: ["on_field_dps"],
  ability_categories: ["basic"],
  verification_status: "verified",
  analysis_status: "completed",
  availability: {facts: true, abilities: true, analysis: true, sources: true},
  completeness: {identity: 1, combat: 1, narrative: 0.5, presentation: 0, analysis: 1},
};

const listResponse = {
  schema_version: "web-reference-character-list/0.1",
  characters: [summary],
  total: 1,
};

test("listReferenceCharacters sends typed search and filter query parameters", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(JSON.stringify(listResponse), {status: 200});
  };

  try {
    const response = await apiClient.listReferenceCharacters({q: "简·杜", ip: "Zenless Zone Zero", combat_role: "on_field_dps"});
    assert.equal(response.characters[0].display_name, "Jane Doe");
    assert.match(requestedUrl, /q=%E7%AE%80%C2%B7%E6%9D%9C/);
    assert.match(requestedUrl, /ip=Zenless\+Zone\+Zero/);
    assert.match(requestedUrl, /combat_role=on_field_dps/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("reference list rejects a successful response that drifts from the frozen contract", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({schema_version: "web-reference-character-list/0.2", characters: [], total: 0}), {status: 200});

  try {
    await assert.rejects(
      () => apiClient.listReferenceCharacters(),
      (error: unknown) => error instanceof ApiClientError && error.payload.error.code === "REFERENCE_CHARACTER_LIST_INVALID",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("reference detail keeps a safe API error for a missing record", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({error: {
    code: "REFERENCE_CHARACTER_NOT_FOUND",
    message: "The requested reference character was not found.",
    stage: "reference_corpus",
    retryable: false,
    details: {},
    audit: null,
  }}), {status: 404});

  try {
    await assert.rejects(
      () => apiClient.getReferenceCharacter("no-such-record"),
      (error: unknown) => error instanceof ApiClientError && error.statusCode === 404 && error.payload.error.code === "REFERENCE_CHARACTER_NOT_FOUND",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
