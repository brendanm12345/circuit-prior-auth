import { NextResponse } from "next/server"
import { z } from "zod";
import { promises as fs } from 'fs';
import { join } from 'path';

const requestBodySchema = z.object({
    insurance_provider: z.enum(["anthem", "aetna"]),
    insurance_plan: z.string(),
    drug_name: z.string(),
});

export async function POST(request: Request) {
    const body = await request.json();
    const parseResult = requestBodySchema.safeParse(body);

    if (!parseResult.success) {
        return new Response(JSON.stringify({ error: "Invalid request body" }), { status: 400 });
    }

    switch (parseResult.data.insurance_provider) {
        case "anthem":
            const llmPrompt = await handleAnthem(parseResult.data.drug_name);
            return NextResponse.json({ message: llmPrompt });
        case "aetna":
            const aetnaPrompt = await handleAetna(parseResult.data.drug_name);
            return NextResponse.json({ message: aetnaPrompt });
        default:
            return new Response(JSON.stringify({ error: "Invalid insurance provider" }), { status: 400 });
    }
}

const readFile = async (insuranceProvider: "anthem" | "aetna") => {
    const filePath = join(process.cwd(), `app/api/multion/prompts/${insuranceProvider}.txt`);
    return await fs.readFile(filePath, 'utf-8');
}

const handleAnthem = async (drugName: string) => {
    let anthemContent = await readFile("anthem");
    anthemContent = anthemContent.replace("${DRUG_NAME}", drugName);
    return anthemContent;
}

const handleAetna = async (drugName: string) => {
    let aetnaContent = await readFile("aetna");
    aetnaContent = aetnaContent.replace("${DRUG_NAME}", drugName);
    return aetnaContent;
}