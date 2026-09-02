import type {CharacterValidationResponse, RawCharacterResult} from "../../../../lib/api/types";

export function RawDebugView({raw, validation}: {raw: RawCharacterResult; validation: CharacterValidationResponse | null}) {
  return (
    <div>
      <p className="debug-label">Developer-only surface · not a core UI data source</p>
      <h3 className="subheading">Generation response</h3>
      <pre className="json-view">{JSON.stringify(raw, null, 2)}</pre>
      {validation && <><h3 className="subheading debug-subheading">Validation response</h3><pre className="json-view">{JSON.stringify(validation, null, 2)}</pre></>}
    </div>
  );
}
