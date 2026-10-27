import { render, screen } from "@testing-library/react";
import { GuildValues } from "./GuildValues";

describe("GuildValues", () => {
  it("renders nothing when the text is blank", () => {
    const { container } = render(<GuildValues text={"  \n\n "} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("splits stanzas on blank lines, keeps verses, and shows the guild name", () => {
    render(<GuildValues text={"Entraide,\nbonne humeur.\n\nMon panache."} author="Les Zouaves" />);
    const stanzas = screen.getAllByRole("paragraph");
    expect(stanzas.map((p) => p.textContent)).toEqual(["Entraide,\nbonne humeur.", "Mon panache."]);
    expect(screen.getByText("Les Zouaves")).toBeInTheDocument();
  });
});
