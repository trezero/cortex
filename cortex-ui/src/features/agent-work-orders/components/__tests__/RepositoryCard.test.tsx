/**
 * RepositoryCard Component Tests
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ConfiguredRepository } from "../../types/repository";
import { RepositoryCard } from "../RepositoryCard";

const mockRepository: ConfiguredRepository = {
  id: "repo-1",
  repository_url: "https://github.com/test/repository",
  display_name: "repository",
  owner: "test",
  default_branch: "main",
  is_verified: true,
  last_verified_at: "2024-01-01T00:00:00Z",
  default_sandbox_type: "git_worktree",
  default_commands: ["create-branch", "planning", "execute"],
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("RepositoryCard", () => {
  it("renders short repository name", () => {
    render(<RepositoryCard repository={mockRepository} stats={{ total: 5, active: 2, done: 3 }} />);
    expect(screen.getByText("repository")).toBeInTheDocument();
  });

  it("calls onSelect when clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(<RepositoryCard repository={mockRepository} onSelect={onSelect} stats={{ total: 0, active: 0, done: 0 }} />);

    const card = screen.getByRole("button", { name: /repository/i });
    await user.click(card);

    expect(onSelect).toHaveBeenCalledOnce();
  });

  it("shows copy action and no edit/delete actions", () => {
    render(<RepositoryCard repository={mockRepository} stats={{ total: 0, active: 0, done: 0 }} />);

    expect(screen.getByLabelText("Copy repository URL")).toBeInTheDocument();
    expect(screen.queryByLabelText("Edit repository")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Delete repository")).not.toBeInTheDocument();
  });
});
