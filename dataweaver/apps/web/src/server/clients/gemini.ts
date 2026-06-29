import { GoogleGenAI } from '@google/genai';
import { getServiceConfig } from '~/server/config';

let _genAI: GoogleGenAI | null = null;

const getGenAI = (): GoogleGenAI => {
  if (!_genAI) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey)
      throw new Error('GEMINI_API_KEY environment variable is not set');
    const config = getServiceConfig();
    _genAI = new GoogleGenAI({ apiKey, apiVersion: config.gemini.apiVersion });
  }
  return _genAI;
};

export { getGenAI };
