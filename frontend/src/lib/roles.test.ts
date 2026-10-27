import { isOfficerOrAbove, LOGIN_ERRORS, outranks, ROLE_LABELS } from "./roles";

describe("roles", () => {
  it("labels every role in French", () => {
    expect(ROLE_LABELS).toEqual({ member: "Membre", officer: "Officier", gm: "GM" });
  });

  it("ranks officers and GM above members", () => {
    expect(isOfficerOrAbove("member")).toBe(false);
    expect(isOfficerOrAbove("officer")).toBe(true);
    expect(isOfficerOrAbove("gm")).toBe(true);
  });

  it("only lets a strictly higher rank act on a target", () => {
    expect(outranks("officer", "member")).toBe(true);
    expect(outranks("officer", "officer")).toBe(false);
    expect(outranks("gm", "officer")).toBe(true);
    expect(outranks("member", "gm")).toBe(false);
  });

  it("has a message for every backend error code", () => {
    const backendCodes = [
      "not_member",
      "missing_role",
      "deactivated",
      "discord_denied",
      "state_mismatch",
      "discord_error",
    ];
    for (const code of backendCodes) expect(LOGIN_ERRORS[code]).toBeTruthy();
  });
});
