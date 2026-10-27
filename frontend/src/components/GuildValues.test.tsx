import { render, screen } from "@testing-library/react";
import { GuildValues } from "./GuildValues";

describe("GuildValues", () => {
  it("renders nothing when the text is blank", () => {
    const { container } = render(<GuildValues text={"  \n\n "} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("splits paragraphs on blank lines and shows the guild name", () => {
    render(<GuildValues text={"Entraide.\n\nBonne humeur."} author="Les Zouaves" />);
    expect(screen.getByText("Entraide.")).toBeInTheDocument();
    expect(screen.getByText("Bonne humeur.")).toBeInTheDocument();
    expect(screen.getByText("Les Zouaves")).toBeInTheDocument();
  });
});
