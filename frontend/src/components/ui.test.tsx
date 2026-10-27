import { render, screen } from "@testing-library/react";
import { RoleBadge } from "./ui";

describe("RoleBadge", () => {
  it("shows the French label of the role", () => {
    render(<RoleBadge role="officer" />);
    expect(screen.getByText("Officier")).toBeInTheDocument();
  });
});
