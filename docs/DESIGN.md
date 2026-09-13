# Interface design

The report is an inspection workspace. Its visual hierarchy should lead from usage, to session, to response, to evidence. The presentation should stay quiet enough to compare values without reading promotional copy or navigating a wall of cards.

## Research applied

- [Nielsen Norman Group: Clutter-Free Charts](https://www.nngroup.com/articles/clutter-charts/) recommends removing visual elements that distract from the data and choosing axes/labels according to the comparison being made. Here, the response chart keeps a zero baseline and three reference lines; decorative backgrounds, shadows and competing accents are removed.
- [GOV.UK Design System: Tables](https://design-system.service.gov.uk/components/table/) provides guidance for readable comparative data, including numerical alignment. Usage Lens applies consistent right alignment and tabular numerals to its count/value pairs. The response breakdown uses a semantic definition list, because it is a single record rather than a multirecord table.
- [WAI-ARIA Authoring Practices: Tabs](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) defines tab roles, selection state, relationships and keyboard operation. The four detail views use tab/tabpanel semantics, roving focus, arrow keys, Home and End.

These sources inform the decisions; this is an original interface, not a copy of a design system or a claim of certification.

## Decisions

**One working surface.** Plain backgrounds, thin separators and modest headings replace the earlier rounded-card layout, decorative section labels, slogan and large branded header.

**Overview numbers have one level of emphasis.** Four unboxed readouts summarize the active filters. Totals use restrained display precision; exact recorded counts and finer credit allocation stay available in response detail. Partial estimates remain labeled beside the number.

**The chart is the main visual.** Neutral grays describe input. Blue shades distinguish output. Series have a labeled legend and textual values in the response view; color is not the only way to inspect usage. Chart dimensions and tick density adapt to the available width.

**Details follow selection.** Response is the default view. Findings, Activity and Coverage have separate tabs. Following evidence returns to the corresponding response, including across pages. Rates and source provenance use disclosures; recorded speed assumptions and unavailable estimates remain visible near their values.

**Session navigation stays compact.** Rows show the session title, model/date, token count and estimated credits. The full project path is in the selected-session heading and row tooltip. On smaller screens, an explicit Browse control reveals the session list.

**Minimal does not mean hidden controls.** Inputs and buttons retain recognizable boundaries, visible keyboard focus and native semantics. The interface includes a skip link and separate light/dark palettes. No remote fonts, scripts, icons or visual assets are required.

## Checks

The synthetic browser suite exercises tabs and keyboard navigation, mobile session browsing, bar/selector synchronization, evidence links, filters, refresh, empty states and both appearances. Screenshots cover 360, 736, 1,024 and 1,440 px. The checks verify behavior and layout; they do not replace usability testing with people who use Codex.

## Combined workspace

Agent Ledger adds Start, Search, Saved context, Usage, and Connect an agent as plain navigation in one local browser app. Start leads with a useful question and a compact search field, then distinct measured patterns and recent work. Each pattern offers an explanation, one practical next step, a copyable prompt, and direct evidence. No score or savings estimate is invented.

Search results open source excerpts with surrounding messages; a takeaway is written deliberately in the note editor rather than silently extracted. Project scope is shared across views. Agent setup explains the background process and data boundary before showing a configuration. The calendar and detailed chart are subordinate to these tasks. New layouts retain text-only rendering, visible focus, light/dark palettes, and narrow-screen stacking.
