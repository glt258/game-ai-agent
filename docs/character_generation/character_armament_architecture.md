# Character Armament Architecture

## Audit result

The current Character Generation implementation does **not** hard-code a weapon
category. The generation draft uses `combat_role_profile` for a high-level combat role such as
support; damage-pattern language such as burst remains free-form design semantics and is
not a role field. The profile is not used as an armament type.

The formal character schema uses `combat.tentative_role`, `combat.notes`, and a free-form
`tags` array. It has no `weapon_type`, `weapon_class`, `WeaponType`, or fixed sword/gun/
spear/bow enum. The Character Generation prompt asks for a high-level combat role and
does not ask the model to select from a weapon list. Existing deterministic fixtures and
evals likewise do not validate weapon categories.

Decision for this audit: **NO CODE CHANGE REQUIRED**.

Adding a `CharacterArmament` field now would create a new output contract without a
current fixed-weapon constraint to migrate, and would rewrite the frozen Character
Generation baseline unnecessarily. The current free-form brief and design fields can
carry future armament design without blocking a later explicit schema extension.

## Character Armament

When this concept is added to the character schema in a future version, it should mean
the character's signature combat expression:

```text
Character-bound
Non-equipable
Free-form
Part of character identity and action presentation
```

The form should remain a free string. Valid examples include an umbrella, camera,
playing cards, paired pistols, instrument, silk thread, or bare hands. Any future
mechanical range vocabulary should describe combat behaviour, not weapon families.

Do not introduce a global enum such as `Sword`, `Gun`, `Spear`, `Greatsword`, `Bow`, or
`Catalyst` as a generation restriction. Do not turn a character's armament into an
`allowed_weapon_type` or `weapon_requirement` gate.

## Mechanic tags

The current Character Generation draft does not have a dedicated `mechanic_tags` field;
it has free-form `new_design_elements`, `ability_concept`, and `tags` in the formal
character data schema. No compatibility calculation or tag enum is introduced by this
audit. If a later schema needs tags for equipment synergy, they should remain deduplicated
free strings and should describe mechanics such as `on_field`, `dodge_trigger`, or
`resource_builder_spender`.

## Future WeaponModule seam

`WeaponModule` and Artifact/Equipment Sets are future, separate, equipable systems. They
are not implemented here. Their compatibility should be expressed through mechanic tags
and soft synergy, not by replacing or locking the character's signature combat medium.

```text
signature_owner != exclusive_owner
```

A future signature module may be especially suitable for a character without becoming a
hard character lock. Reference Corpus native taxonomies remain independent from this
project's future equipment design and are intentionally unchanged.
