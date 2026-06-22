# -*- coding: utf-8 -*-
import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/api/whoami", response_class=JSONResponse)
def whoami():
    return {
        "app": "RetailVision",
        "cwd": os.getcwd(),
        "file": __file__,
    }
