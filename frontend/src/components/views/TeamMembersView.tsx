"use client";

import React, { useState } from "react";
import {
  Users,
  Plus,
  Shield,
  UserCheck,
  UserX,
  Mail,
  Award,
  ArrowRight,
  Info,
  Building2,
  FolderGit2,
} from "lucide-react";
import { useLiveApp } from "../../context/LiveAppContext";
import { AdminPage } from "../figma-pages/AdminPage";

export function TeamMembersView() {
  const {
    activeProject,
    activeOrg,
    members,
    isLoadingMembers,
    setIsAddMemberModalOpen,
    updateMember,
  } = useLiveApp();

  const [activeTab, setActiveTab] = useState<"project" | "org">(
    activeProject ? "project" : "org"
  );

  const handleRoleChange = async (memberId: string, transitionRole: string) => {
    try {
      await updateMember(memberId, {
        transition_role: transitionRole || undefined,
      });
    } catch (err) {
      console.error(err);
    }
  };

  // If no project is selected, render the Organisation Directory directly
  if (!activeProject || activeTab === "org") {
    return (
      <div className="space-y-6">
        {/* Scope switcher if project is active */}
        {activeProject && (
          <div className="flex items-center gap-2 border-b border-[#DCE3EB] pb-3">
            <button
              type="button"
              onClick={() => setActiveTab("project")}
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 border border-[#DCE3EB] bg-white text-[#69778D] hover:text-[#25334B] hover:bg-slate-50 transition-colors"
            >
              <FolderGit2 className="w-3.5 h-3.5" />
              <span>Project Transition Roles ({members.length})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("org")}
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 bg-[#4774A9] text-white shadow-2xs"
            >
              <Building2 className="w-3.5 h-3.5" />
              <span>Organisation Members Directory</span>
            </button>
          </div>
        )}

        {!activeProject && (
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-[#4774A9]" />
              <span>
                Showing organisation directory for <strong>{activeOrg?.name || "Organisation"}</strong>. Select a project workspace from the top bar to configure project-specific transition roles.
              </span>
            </div>
          </div>
        )}

        <AdminPage view="team" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 1. Header */}
      <div className="bg-white rounded-xl border border-[#DCE3EB] p-5 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-[#4774A9] uppercase tracking-wider">
            <span>Project Workspace Team</span>
            <span className="w-1.5 h-1.5 rounded-full bg-[#249E91]" />
            <span className="text-[#69778D] font-normal">{activeProject.name}</span>
          </div>
          <h1 className="text-xl font-bold text-[#25334B] mt-1 tracking-tight">
            Team Members &amp; Transition Roles
          </h1>
          <p className="text-xs text-[#69778D] mt-0.5">
            Configure project contributors and assign transition responsibilities (Departing Owner, Incoming Assignee, Reviewer, Observer).
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            type="button"
            onClick={() => setActiveTab("org")}
            className="px-3 py-2 rounded-lg border border-[#DCE3EB] bg-white hover:bg-slate-50 text-[#25334B] text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-2xs"
          >
            <Building2 className="w-3.5 h-3.5 text-[#69778D]" />
            <span>Organisation Directory</span>
          </button>
          <button
            type="button"
            onClick={() => setIsAddMemberModalOpen(true)}
            className="px-4 py-2 rounded-lg bg-[#4774A9] hover:bg-[#365F92] text-white text-xs font-semibold flex items-center gap-2 transition-colors shadow-xs"
          >
            <Plus className="w-4 h-4" />
            <span>Add Team Member</span>
          </button>
        </div>
      </div>

      {/* 2. Information Banner */}
      <div className="p-4 rounded-xl bg-sky-50/70 border border-sky-200 flex items-start gap-3 text-xs text-sky-950">
        <Info className="w-4 h-4 text-[#4774A9] shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <span className="font-semibold">Handover Governance Rule:</span> Handover packages require formal approval by a designated <strong>Reviewer</strong>. The <strong>Incoming Assignee</strong> acknowledges receipt, which cannot substitute for reviewer approval.
        </div>
      </div>

      {/* 3. Members Table */}
      <div className="bg-white rounded-xl border border-[#DCE3EB] shadow-2xs overflow-hidden">
        <div className="px-5 py-3.5 border-b border-[#DCE3EB] bg-[#F4F6F9] flex items-center justify-between text-xs font-semibold text-[#69778D]">
          <span>Project Participant ({members.length})</span>
          <span>Transition Responsibility</span>
        </div>

        {members.length === 0 ? (
          <div className="p-8 text-center">
            <Users className="w-10 h-10 text-[#69778D] mx-auto mb-2 opacity-50" />
            <div className="text-xs font-semibold text-[#25334B]">No Members Configured</div>
            <p className="text-[11px] text-[#69778D] mt-1">
              Add colleagues to this workspace to assign transition roles.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-[#DCE3EB]">
            {members.map((member) => (
              <div
                key={member.id}
                className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-[#F4F6F9]/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-[#253650] text-white font-bold text-xs flex items-center justify-center shrink-0 border border-[#249E91]/40">
                    {member.user_full_name ? member.user_full_name.charAt(0).toUpperCase() : "U"}
                  </div>
                  <div>
                    <div className="font-semibold text-xs text-[#25334B] flex items-center gap-2">
                      <span>{member.user_full_name || "Workspace Member"}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#E8EEF5] text-[#4774A9] font-medium">
                        {member.role_name.replace("project_", "").toUpperCase()}
                      </span>
                    </div>
                    <div className="text-[11px] text-[#69778D] flex items-center gap-1.5 mt-0.5">
                      <Mail className="w-3 h-3 text-[#69778D]" />
                      <span>{member.user_email || "user@org.internal"}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <select
                    value={member.transition_role || ""}
                    onChange={(e) => handleRoleChange(member.id, e.target.value)}
                    className="px-3 py-1.5 rounded-lg border border-[#DCE3EB] text-xs font-semibold text-[#25334B] bg-white focus:outline-none focus:ring-1 focus:ring-[#4774A9]"
                  >
                    <option value="">No Transition Role</option>
                    <option value="departing_owner">Departing Knowledge Owner</option>
                    <option value="incoming_assignee">Incoming Assignee</option>
                    <option value="reviewer">Handover Reviewer (Approver)</option>
                    <option value="observer">Transition Observer</option>
                  </select>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
