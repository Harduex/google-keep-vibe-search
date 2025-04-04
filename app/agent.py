"""
AI Agent functionality for autonomous search and context enrichment.
"""
import json
import logging
import time
from typing import Dict, List, Any, Tuple, Optional
import os

import requests

from app.config import (
    AGENT_SEARCH_TIMEOUT,
    ENABLE_AI_AGENT_MODE,
    MAX_AGENT_SEARCHES,
    AI_AGENT_LOG_FILE,
    OLLAMA_API_URL,
    LLM_MODEL
)
from app.search import VibeSearch

# Configure logging for agent operations
logging.basicConfig(
    filename=AI_AGENT_LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ai_agent")

class AIAgent:
    """
    AI Agent that autonomously determines if additional searches are needed
    and executes them to enrich the context for the chatbot.
    """
    def __init__(self, search_engine: VibeSearch):
        """Initialize the AI Agent with a search engine."""
        self.search_engine = search_engine
        self.api_url = OLLAMA_API_URL
        self.model = LLM_MODEL
        self.enabled = ENABLE_AI_AGENT_MODE
        self.actions = []  # Track agent actions for display to the user
    
    def evaluate_context(self, query: str, current_context: List[Dict[str, Any]]) -> bool:
        """
        Evaluate whether the current context is sufficient for answering the query.
        
        Args:
            query: The user's query
            current_context: The current notes context
            
        Returns:
            Boolean indicating whether additional searches are needed
        """
        if not self.enabled or not query:
            return False
            
        logger.info(f"Evaluating context for query: {query}")
        self.actions.append({
            "type": "evaluate_context",
            "description": f"Evaluating if I need more context for: '{query}'"
        })
        
        # If no context was found, definitely need to search
        if not current_context:
            logger.info("No initial context found, additional search needed")
            self.actions.append({
                "type": "decision",
                "description": "No initial context found. I need to search for information."
            })
            return True
            
        # Define criteria for evaluating context
        try:
            # Prepare evaluation prompt with context and query
            notes_context = self._format_notes_for_evaluation(current_context)
            
            eval_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an AI assistant tasked with evaluating whether the provided context "
                        "is sufficient to answer a user query comprehensively. "
                        "Analyze the context and the query, and determine if more information is needed. "
                        "Respond with JSON: {'needs_more_context': true/false, 'reason': 'explanation', 'suggested_search_query': 'query'}"
                    )
                },
                {
                    "role": "user", 
                    "content": (
                        f"Context:\n{notes_context}\n\nQuery: {query}\n\n"
                        f"Is this context sufficient to answer the query? Respond with JSON."
                    )
                }
            ]
            
            # Make evaluation request to the LLM
            start_time = time.time()
            evaluation = self._call_llm_for_evaluation(eval_messages)
            elapsed_time = time.time() - start_time
            
            logger.info(f"Context evaluation completed in {elapsed_time:.2f} seconds")
            logger.info(f"Evaluation result: {evaluation}")
            
            needs_more = evaluation.get("needs_more_context", False)
            reason = evaluation.get("reason", "No reason provided")
            
            if needs_more:
                self.actions.append({
                    "type": "decision",
                    "description": f"I need more information: {reason}"
                })
            else:
                self.actions.append({
                    "type": "decision",
                    "description": f"I have sufficient context to answer the question."
                })
                
            return needs_more
            
        except Exception as e:
            logger.error(f"Error during context evaluation: {str(e)}")
            self.actions.append({
                "type": "error",
                "description": f"Error evaluating context: {str(e)}"
            })
            # Default to not needing more context in case of error
            return False
    
    def generate_search_queries(self, query: str, current_context: List[Dict[str, Any]]) -> List[str]:
        """
        Generate additional search queries based on the original query and current context.
        
        Args:
            query: The original user query
            current_context: The current notes context
            
        Returns:
            List of generated search queries
        """
        logger.info(f"Generating additional search queries for: {query}")
        self.actions.append({
            "type": "generate_queries",
            "description": "Generating search queries to find relevant information"
        })
        
        try:
            # Check if we have any context
            if not current_context:
                logger.info("No initial context - using direct search approach")
                # If no context, use a simplified prompt that doesn't reference existing context
                query_gen_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an AI search assistant tasked with generating effective search queries. "
                            "Your goal is to help find information in a collection of personal notes. "
                            "Based on the user's query, generate up to 3 search queries that will help find relevant information. "
                            "Focus on different angles and potential keywords that would appear in relevant notes. "
                            "Respond with JSON: {'search_queries': ['query1', 'query2', 'query3']}"
                        )
                    },
                    {
                        "role": "user", 
                        "content": (
                            f"Query: {query}\n\n"
                            f"Generate search queries to find relevant information in a collection of personal notes."
                        )
                    }
                ]
                
                # Call LLM to generate search queries
                result = self._call_llm_for_evaluation(query_gen_messages)
                
                # Extract generated queries
                search_queries = result.get("search_queries", [])
                # Ensure we don't have too many queries
                search_queries = search_queries[:MAX_AGENT_SEARCHES]
                
                # If somehow no queries were generated, use the original query
                if not search_queries:
                    search_queries = [query] 
                    
                logger.info(f"Generated search queries (no context): {search_queries}")
                
                # Log each query as an action
                for idx, sq in enumerate(search_queries):
                    self.actions.append({
                        "type": "query",
                        "description": f"Search query {idx+1}: '{sq}'"
                    })
                    
                return search_queries
            
            # Format existing context
            context_str = self._format_notes_for_evaluation(current_context)
            
            # Prepare prompt for search query generation with context
            query_gen_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an AI search assistant tasked with generating effective search queries. "
                        "Based on the user's original query and the context already provided, "
                        "generate up to 2 additional search queries that would help find more relevant information. "
                        "Focus on identifying missing information or specific details that would help answer the query more comprehensively. "
                        "Respond with JSON: {'search_queries': ['query1', 'query2']}"
                    )
                },
                {
                    "role": "user", 
                    "content": (
                        f"Original query: {query}\n\n"
                        f"Current context:\n{context_str}\n\n"
                        f"Generate additional search queries to find more relevant information."
                    )
                }
            ]
            
            # Call LLM to generate search queries
            result = self._call_llm_for_evaluation(query_gen_messages)
            
            # Extract generated queries
            search_queries = result.get("search_queries", [])
            # Ensure we don't have too many queries
            search_queries = search_queries[:MAX_AGENT_SEARCHES]
            
            logger.info(f"Generated search queries: {search_queries}")
            
            # Log each query as an action
            for idx, sq in enumerate(search_queries):
                self.actions.append({
                    "type": "query",
                    "description": f"Search query {idx+1}: '{sq}'"
                })
                
            return search_queries
            
        except Exception as e:
            logger.error(f"Error generating search queries: {str(e)}")
            self.actions.append({
                "type": "error",
                "description": f"Error generating search queries: {str(e)}"
            })
            # Return the original query as a fallback
            self.actions.append({
                "type": "query",
                "description": f"Falling back to original query: '{query}'"
            })
            return [query]
    
    def execute_searches(self, search_queries: List[str], max_results_per_query: int = 3) -> List[Dict[str, Any]]:
        """
        Execute multiple search queries and return the combined results.
        
        Args:
            search_queries: List of search queries to execute
            max_results_per_query: Maximum number of results to return per query
            
        Returns:
            Combined list of search results
        """
        all_results = []
        result_ids = set()  # Track note IDs to avoid duplicates
        
        self.actions.append({
            "type": "search",
            "description": f"Executing {len(search_queries)} search queries"
        })
        
        for query in search_queries:
            try:
                logger.info(f"Executing search: {query}")
                results = self.search_engine.search(query, max_results=max_results_per_query)
                
                # Add only new results (avoid duplicates)
                new_results = 0
                for result in results:
                    # Use ID or combination of title+content as unique identifier
                    result_id = result.get("id", f"{result.get('title', '')}-{result.get('content', '')[:50]}")
                    if result_id not in result_ids:
                        result["added_by_agent"] = True  # Mark all results as added by agent
                        all_results.append(result)
                        result_ids.add(result_id)
                        new_results += 1
                        
                logger.info(f"Search '{query}' returned {len(results)} results, {len(all_results)} unique results so far")
                self.actions.append({
                    "type": "result",
                    "description": f"Found {new_results} new notes for query: '{query}'"
                })
                
            except Exception as e:
                logger.error(f"Error executing search '{query}': {str(e)}")
                self.actions.append({
                    "type": "error",
                    "description": f"Error searching for '{query}': {str(e)}"
                })
        
        if not all_results:
            self.actions.append({
                "type": "result",
                "description": "No relevant notes found for any search queries"
            })
        else:
            self.actions.append({
                "type": "summary",
                "description": f"Found a total of {len(all_results)} relevant notes"
            })
            
        return all_results
    
    def process_query(self, query: str, initial_context: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """
        Process a user query, evaluating context and performing additional searches if needed.
        
        Args:
            query: The user's query
            initial_context: The initial notes context
            
        Returns:
            Tuple of (enriched context with additional relevant notes, list of agent actions)
        """
        # Reset actions list for this query
        self.actions = []
        
        if not self.enabled:
            logger.info("AI Agent mode is disabled, using initial context only")
            return initial_context, self.actions
            
        try:
            logger.info(f"Processing query with AI Agent: {query}")
            logger.info(f"Initial context has {len(initial_context)} notes")
            
            self.actions.append({
                "type": "start",
                "description": f"Starting to process query: '{query}'"
            })
            
            # Start timing the agent process
            start_time = time.time()
            
            # If initial_context is empty, we know we need to perform search
            needs_more_context = True if not initial_context else self.evaluate_context(query, initial_context)
            
            if not needs_more_context:
                logger.info("Initial context deemed sufficient")
                self.actions.append({
                    "type": "complete",
                    "description": "Initial context is sufficient, no additional searches needed"
                })
                return initial_context, self.actions
            
            # Generate additional search queries
            search_queries = self.generate_search_queries(query, initial_context)
            
            if not search_queries:
                logger.info("No additional search queries generated")
                self.actions.append({
                    "type": "complete",
                    "description": "No search queries could be generated"
                })
                return initial_context, self.actions
            
            # Execute additional searches
            additional_results = self.execute_searches(search_queries)
            
            if not additional_results:
                logger.info("No search results found")
                self.actions.append({
                    "type": "complete", 
                    "description": "No relevant notes found in searches"
                })
                return initial_context, self.actions
                
            # Combine initial context with additional results (avoid duplicates)
            initial_ids = {note.get("id", f"{note.get('title', '')}-{note.get('content', '')[:50]}") 
                          for note in initial_context}
            
            enriched_context = initial_context.copy()
            
            for note in additional_results:
                note_id = note.get("id", f"{note.get('title', '')}-{note.get('content', '')[:50]}")
                if note_id not in initial_ids:
                    note["added_by_agent"] = True  # Ensure all added notes are marked
                    enriched_context.append(note)
            
            elapsed_time = time.time() - start_time
            logger.info(f"AI Agent processing completed in {elapsed_time:.2f} seconds")
            logger.info(f"Enriched context now has {len(enriched_context)} notes (+{len(enriched_context) - len(initial_context)})")
            
            # Check if we've exceeded the timeout
            if elapsed_time > AGENT_SEARCH_TIMEOUT:
                logger.warning(f"AI Agent processing exceeded timeout: {elapsed_time:.2f}s > {AGENT_SEARCH_TIMEOUT}s")
                self.actions.append({
                    "type": "warning",
                    "description": f"Processing took longer than expected: {elapsed_time:.1f}s"
                })
            
            # Add final summary action
            added_notes_count = len(enriched_context) - len(initial_context)
            self.actions.append({
                "type": "complete",
                "description": f"Added {added_notes_count} new notes to help answer your question"
            })
            
            return enriched_context, self.actions
            
        except Exception as e:
            logger.error(f"Error in AI Agent processing: {str(e)}")
            self.actions.append({
                "type": "error",
                "description": f"Error processing query: {str(e)}"
            })
            # Return initial context in case of error
            return initial_context, self.actions
    
    def _call_llm_for_evaluation(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Call the LLM to evaluate context or generate search queries.
        
        Args:
            messages: The list of message objects for the LLM
            
        Returns:
            Parsed JSON response from the LLM
        """
        try:
            # Prepare the API request payload
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False
            }
            
            logger.debug(f"Preparing LLM call with messages: {messages}")
            
            # Make the API request
            response = requests.post(
                f"{self.api_url}/api/chat",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=AGENT_SEARCH_TIMEOUT
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Extract the content from the response
            content = response_data.get("message", {}).get("content", "")
            
            logger.debug(f"LLM response content: {content}")
            
            # Try to parse JSON from the response
            # Sometimes the LLM might include markdown code fences or other text
            # Try to extract JSON content if needed
            try:
                # First attempt direct parse
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                import re
                json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(1))
                    return result
                    
                # If that fails, try to find any JSON-like structure with braces
                json_match = re.search(r'({.*})', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(1))
                    return result
                
                # Return a default response if no JSON is found
                logger.warning(f"Could not extract JSON from LLM response: {content}")
                return {"needs_more_context": False, "reason": "Failed to parse LLM response"}
                
        except Exception as e:
            logger.error(f"Error calling LLM for evaluation: {str(e)}")
            # Return a default response in case of error
            return {"needs_more_context": False, "reason": f"Error: {str(e)}"}
    
    def _format_notes_for_evaluation(self, notes: List[Dict[str, Any]]) -> str:
        """Format notes into a string for LLM evaluation."""
        formatted_notes = []
        
        for i, note in enumerate(notes):
            title = note.get("title", "Untitled Note")
            content = note.get("content", "")
            # Use a shorter format for evaluation to save tokens
            formatted_notes.append(f"Note {i+1}: {title} - {content[:200]}...")
        
        return "\n".join(formatted_notes)