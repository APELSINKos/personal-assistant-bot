import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { LangProvider } from "../i18n";
import { useTextLimit } from "./TextLimit";

function Field({ max }: { max: number }) {
  const [text, setText] = useState("");
  const limit = useTextLimit(text.trim(), max);
  return (
    <>
      <input aria-label="Поле" value={text} {...limit.field} onChange={(event) => setText(event.target.value)} />
      {limit.hint}
    </>
  );
}

describe("useTextLimit", () => {
  it("counts in characters and says how long a text over the limit is, where a screen reader listens", () => {
    const { container } = render(
      <LangProvider lang="ru">
        <Field max={3} />
      </LangProvider>,
    );
    const field = screen.getByRole("textbox", { name: "Поле" });
    // The region is there before anything is said in it.
    const region = container.querySelector('[aria-live="polite"]');
    expect(region).toBeEmptyDOMElement();
    expect(field).toHaveAttribute("aria-invalid", "false");
    expect(field).not.toHaveAttribute("aria-describedby");

    fireEvent.change(field, { target: { value: " 😀😀😀 " } }); // three characters in six UTF-16 units
    expect(region).toBeEmptyDOMElement();

    fireEvent.change(field, { target: { value: "😀😀😀😀" } });
    expect(region).toHaveTextContent("4/3");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription("4/3");
    expect(field).toHaveValue("😀😀😀😀"); // nothing cut off
  });
});
