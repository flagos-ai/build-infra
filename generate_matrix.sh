#!/bin/bash

# Script to generate a GitHub Actions matrix from vendor JSON files
generate_matrix() {
    local vendors=("amd" "ascend" "matex" "nvidia")
    local all_objects=()
    

    # Loop through each vendor and collect all JSON objects
    for vendor in "${vendors[@]}"; do
        local json_file="vendor_json/${vendor}.json"
        
        if [[ -f "$json_file" ]]; then
            # Use jq if available to properly parse JSON
            if command -v jq &> /dev/null; then
                # Get the number of objects in the array
                local count=$(jq 'length' "$json_file")
                # Extract each object and add missing properties
                for ((i = 0; i < count; i++)); do
                    local obj=$(jq ".[$i]" "$json_file")
                    all_objects+=("$obj")
                done
            else
                # Fallback method if jq is not available
                echo "Error: jq command is required but not found." >&2
                exit 1
            fi
        else
            echo "Warning: $json_file does not exist." >&2
        fi
    done
    
    # Create the matrix JSON structure for GitHub Actions
    local matrix_json='{"include": ['
    local first_obj=true
    for obj in "${all_objects[@]}"; do
        # Clean the object by removing newlines and extra spaces
        local clean_obj=$(echo "$obj" | tr '\n' ' ' | sed 's/\s\+/ /g' | sed 's/^ //' | sed 's/ $//')
                
        if [[ "$first_obj" == true ]]; then
            # For the first object, don't add a comma
            matrix_json+="$clean_obj"
            first_obj=false
        else
            # For subsequent objects, add a comma first
            matrix_json+=",$clean_obj"
        fi
    done
    matrix_json+=']}'
    # Output the final matrix JSON
    if command -v jq &> /dev/null; then
        echo "$matrix_json" | jq .
    else
        echo "$matrix_json"
    fi
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    generate_matrix
fi