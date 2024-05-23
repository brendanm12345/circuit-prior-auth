"use client";
import React from "react";
import { Button } from "@/components/ui/button";
// import { supabaseBrowser } from "@/lib/supabase/browser";
import { useRouter, usePathname } from "next/navigation";
import Circuit from "/public/img/circuit.svg";

export default function Navbar() {
    const router = useRouter();

    // const pathname = usePathname();
    // if (pathname === "/login" || pathname === "/") return null;

    return (
        <div className="border-b border-black flex items-center h-[60px] w-full px-6 z-50 fixed bg-white">
            <Circuit height={26} />
        </div>
    );
}
