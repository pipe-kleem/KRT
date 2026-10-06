import maya.cmds as cmds

def get_skin_clusters(mesh):
    """Safely return a list of all skin clusters attached to all shapes of a mesh."""
    shapes = cmds.listRelatives(mesh, shapes=True, fullPath=True) or [mesh]
    history = cmds.listHistory(shapes, pruneDagObjects=True) or []
    skins = cmds.ls(history, type='skinCluster') or []
    return list(set(skins))

# Get current selection
sel = cmds.ls(sl=True)

if len(sel) < 2:
    cmds.warning("Please select the source mesh first, followed by one or more target meshes.")
else:
    src_mesh = sel[0]
    tgt_meshes = sel[1:]

    # 1. Get ALL skin clusters from the source mesh
    src_skins = get_skin_clusters(src_mesh)

    if not src_skins:
        cmds.warning("No skin clusters found on the source mesh: {}".format(src_mesh))
    else:
        for tgt in tgt_meshes:
            cmds.select(cl=True)
            
            # 2. Find and delete ALL existing skin clusters on the target mesh
            tgt_skins = get_skin_clusters(tgt)
            if tgt_skins:
                cmds.delete(tgt_skins)
            
            # 3. Iterate through each skin cluster on the source mesh
            for i, src_skn in enumerate(src_skins):
                # Get the specific influences (joints) for this current skin cluster
                jnts = cmds.skinCluster(src_skn, q=True, inf=True)
                
                new_skn = None
                
                # 4. Handle multiple skin clusters robustly via direct data wiring
                if i == 0:
                    # First cluster: Standard creation works fine
                    new_skn = cmds.skinCluster(jnts, tgt, sm=0, bm=0, omi=False, dr=5, tsb=True)[0]
                else:
                    # Subsequent clusters: Manually wire the deformer to bypass UI limits
                    new_skn = cmds.deformer(tgt, type='skinCluster')[0]
                    
                    # Match the skinning method of the source cluster
                    try:
                        sm_val = cmds.getAttr(src_skn + ".skinningMethod")
                        cmds.setAttr(new_skn + ".skinningMethod", sm_val)
                    except:
                        pass
                    
                    # Manually force the joints into the skin cluster
                    for j, jnt in enumerate(jnts):
                        cmds.connectAttr('{}.worldMatrix[0]'.format(jnt), '{}.matrix[{}]'.format(new_skn, j))
                        bind_pre_mat = cmds.getAttr('{}.worldInverseMatrix[0]'.format(jnt))
                        
                        if isinstance(bind_pre_mat[0], (list, tuple)):
                            bind_pre_mat = bind_pre_mat[0]
                            
                        cmds.setAttr('{}.bindPreMatrix[{}]'.format(new_skn, j), *bind_pre_mat, type='matrix')
                        
                        try:
                            cmds.connectAttr('{}.lockInfluenceWeights'.format(jnt), '{}.lockWeights[{}]'.format(new_skn, j))
                        except:
                            pass
                            
                    # CRITICAL FIX: Initialize the weight array for manually wired clusters
                    # Flooding the first joint with 1.0 weight gives copySkinWeights an array to overwrite
                    cmds.skinPercent(new_skn, tgt, transformValue=[(jnts[0], 1.0)])
                
                cmds.refresh()
                
                # 5. YOUR ORIGINAL LOGIC: Explicitly select source and target before copying
                cmds.select(src_mesh, tgt, r=True)
                
                # Copy the weights using your exact parameters
                cmds.copySkinWeights(
                    ss=src_skn, 
                    ds=new_skn, 
                    sa="closestPoint", 
                    ia="closestJoint", 
                    nm=True, 
                    nr=True
                )
                
        # Reselect the target meshes at the end to match original script flow
        cmds.select(tgt_meshes, r=True)
        print("Successfully copied {} skin cluster(s) from {} to target meshes.".format(len(src_skins), src_mesh))