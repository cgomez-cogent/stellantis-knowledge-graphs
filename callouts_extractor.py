"""Callouts extractor for extracting callout data from XML.

This module extracts callouts from the CALLOUTS section of the XML,
organizing them by IMAGE_REF code with all coordinate and metadata information.
"""

import logging
from typing import Dict
from xml.etree.ElementTree import Element
from utils.helpers import get_text

logger = logging.getLogger(__name__)


class CalloutsExtractor:
    """Extracts callout data from XML."""

    @staticmethod
    def extract_callouts(root: Element, namespace: str, data: Dict) -> None:
        """Extract callouts from CALLOUTS section.

        Populates data['callouts'] with a dictionary where:
        - Key: IMAGE_REF code
        - Value: List of callout objects with coordinates and metadata

        Each callout object contains:
        - ID: Callout identifier
        - DESC: Callout description
        - STARTX, STARTY: Start coordinates
        - ENDX1-ENDX8, ENDY1-ENDY8: Up to 8 endpoint coordinates
        - XT_ID: External identifier

        Args:
            root: Root XML element
            namespace: XML namespace (if any)
            data: Dictionary to populate with callouts

        Returns:
            None (modifies data dict in-place)
        """
        callouts_section = root.find(f'.//{namespace}CALLOUTS' if namespace else './/CALLOUTS')
        if callouts_section is None:
            logger.info("ℹ️ CALLOUTS section not found in XML")
            return

        callouts_dict = {}
        image_refs = callouts_section.findall(f'.//{namespace}IMAGE_REF' if namespace else './/IMAGE_REF')

        for image_ref in image_refs:
            image_ref_code = image_ref.get('CODE')
            if not image_ref_code:
                continue

            callout_list = []
            callouts = image_ref.findall(f'.//{namespace}CALLOUT' if namespace else './/CALLOUT')

            for callout in callouts:
                callout_id = get_text(callout, 'CALLOUT_ID')
                if callout_id:
                    callout_obj = {
                        'ID': callout_id,
                        'DESC': get_text(callout, 'CALLOUT_DESC') or '',
                        'STARTX': get_text(callout, 'STARTX') or '',
                        'STARTY': get_text(callout, 'STARTY') or '',
                        'ENDX1': get_text(callout, 'ENDX1') or '',
                        'ENDY1': get_text(callout, 'ENDY1') or '',
                        'ENDX2': get_text(callout, 'ENDX2') or '',
                        'ENDY2': get_text(callout, 'ENDY2') or '',
                        'ENDX3': get_text(callout, 'ENDX3') or '',
                        'ENDY3': get_text(callout, 'ENDY3') or '',
                        'ENDX4': get_text(callout, 'ENDX4') or '',
                        'ENDY4': get_text(callout, 'ENDY4') or '',
                        'ENDX5': get_text(callout, 'ENDX5') or '',
                        'ENDY5': get_text(callout, 'ENDY5') or '',
                        'ENDX6': get_text(callout, 'ENDX6') or '',
                        'ENDY6': get_text(callout, 'ENDY6') or '',
                        'ENDX7': get_text(callout, 'ENDX7') or '',
                        'ENDY7': get_text(callout, 'ENDY7') or '',
                        'ENDX8': get_text(callout, 'ENDX8') or '',
                        'ENDY8': get_text(callout, 'ENDY8') or '',
                        'XT_ID': get_text(callout, 'XT_ID') or ''
                    }
                    callout_list.append(callout_obj)

            if callout_list:
                callouts_dict[image_ref_code] = callout_list
                logger.debug(f"📌 Found {len(callout_list)} callouts for IMAGE_REF: {image_ref_code}")

        data['callouts'] = callouts_dict
        total_callouts = sum(len(ids) for ids in callouts_dict.values())
        logger.info(f"✅ Extracted {total_callouts} callouts from {len(callouts_dict)} different IMAGE_REFs")
