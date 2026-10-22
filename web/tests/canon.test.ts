import assert from "node:assert/strict";
import test from "node:test";

import {ApiClientError, apiClient} from "../lib/api/client";
import {canonicalEntityHref, isCanonEntityType} from "../features/canon/CanonicalEntityLink";

const summary = {
  entity_id: "faction_005",
  entity_type: "faction",
  name: "临洲市公共安全联席体系",
  aliases: ["Linzhou Public Security Joint Coordination System"],
  summary: "Public coordination system",
  tags: ["public_safety"],
  relation_count: 5,
  visibility: "public",
};

const listResponse = {
  schema_version: "web-canon-entity-list/0.1",
  entities: [summary],
  entity_types: ["faction", "lore", "character", "project", "case", "incident", "story"],
  total: 1,
};

test("Canon client sends q and backend-provided type filters", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(JSON.stringify(listResponse), {status: 200});
  };

  try {
    const response = await apiClient.listCanonEntities({q: "临洲", type: "faction"});
    assert.equal(response.entities[0].entity_id, "faction_005");
    assert.match(requestedUrl, /q=%E4%B8%B4%E6%B4%B2/);
    assert.match(requestedUrl, /type=faction/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Canon client rejects a drifted list contract", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({...listResponse, schema_version: "web-canon-entity-list/0.2"}), {status: 200});
  try {
    await assert.rejects(
      () => apiClient.listCanonEntities(),
      (error: unknown) => error instanceof ApiClientError && error.payload.error.code === "CANON_ENTITY_LIST_INVALID",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Canonical links use encoded stable IDs and explicit entity types", () => {
  assert.equal(canonicalEntityHref("story/one"), "/canon/story%2Fone");
  assert.equal(isCanonEntityType("faction"), true);
  assert.equal(isCanonEntityType("faction_005"), false);
  assert.equal(isCanonEntityType("free-text affiliation"), false);
});

test("Canon detail preserves typed family data and safe not-found errors", async () => {
  const originalFetch = globalThis.fetch;
  const detail = {
    ...summary,
    schema_version: "web-canon-entity/0.1",
    sections: {faction: null, lore: null, character: null, project: null, case: null, incident: null, story: null},
    relationships: [],
    provenance: [],
  };
  globalThis.fetch = async (input) => String(input).includes("missing")
    ? new Response(JSON.stringify({error: {code: "CANON_ENTITY_NOT_FOUND", message: "Not found", stage: "canon", retryable: false, details: {}, audit: null}}), {status: 404})
    : new Response(JSON.stringify(detail), {status: 200});
  try {
    const response = await apiClient.getCanonEntity("faction_005");
    assert.equal(response.entity_type, "faction");
    await assert.rejects(() => apiClient.getCanonEntity("missing"), (error: unknown) => error instanceof ApiClientError && error.statusCode === 404 && error.payload.error.code === "CANON_ENTITY_NOT_FOUND");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
