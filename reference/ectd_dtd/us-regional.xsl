<?xml version="1.0" encoding="UTF-8"?>
<!--version 2-1 Modified to display the revised m1-16 heading and additional m1-16 sub-headings -->
<!--version 2-2 Two additional attributes were added to the m1-15-2-1-material sub-heading-->
<xsl:stylesheet version="2.2" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns="http://www.w3.org/1999/xhtml" xmlns:fo="http://www.w3.org/1999/XSL/Format" xmlns:xlink="http://www.w3c.org/1999/xlink" xmlns:internal="http://www.ich.org" xmlns:fda-regional="http://www.ich.org/fda" xmlns:msxsl="urn:schemas-microsoft-com:xslt" xmlns:js="javascript:code">
	<msxsl:script language="javascript" implements-prefix="js"><![CDATA[
		
		// Vars
		var defFontStr = "font-family: Tahoma, Arial, sans-serif";
		var indent = 1;
		var title = "eCTD";
		var unique = 0;
		var parentTitle;
		var formTitle;
		 
		function getUnique() // Return value of unique counter
		{
			return unique;
		}
				
		function getIndent() // Returns an indent
		{ 
			return indent;
		}
				
		function getCSSRule(ruleNo) // Returns the corresponding CSS rule
		{ 
			if(ruleNo == "0") return defFontStr + "; background-color: white";
			if(ruleNo == "1") return  defFontStr + "; font-size: 16px";
			if(ruleNo == "2") return  defFontStr + "; font-size: 14px";
			if(ruleNo == "3") return  defFontStr + "; font-size: 10px";
			if(ruleNo == "4") return defFontStr + "; font-size: 20px; color: #FFFFFF; background-color: #3366CC; font-weight: bold";
			if(ruleNo == "5") return getCSSRule('2') + "; font-weight: bold; color: #333333; background-color: white";
			if(ruleNo == "6") return defFontStr + "; font-size: 12px; font-weight: bold; color: blue; background-color: #ECECEC";
			if(ruleNo == "7") return  defFontStr + "; font-size: 14px; font-weight: bold; color: #ECECEC; background-color: #ECECEC";
			if(ruleNo == "8") return  "font-family: Verdana, Geneva, Arial, Helvetica, sans-serif; font-size: 14px; font-weight: bold; color: #CCCCCC; background-color: #CCCCCC";
			if(ruleNo == "9") return defFontStr + "; font-size: 12px; font-weight: bold; color: #B9290D; background-color: #ECECEC";
			if(ruleNo == "10") return "font-family: \"MS Sans Serif\"; font-size: 14px; background-color: light-gray";
			if(ruleNo == "11") return defFontStr + "; font-size: 16px; font-weight: bold; color: #FFFFFF";
			if(ruleNo == "12") return "visited {text-decoration: none; color: blue;}";
			if(ruleNo == "13") return "hover {text-decoration: none;color: #047E7D;}";
			if(ruleNo == "14") return "link {text-decoration: none; color: #070BA7; text-decoration: none;}";
			if(ruleNo == "15") return "active {text-decoration: none;}";
			if(ruleNo == "16") return defFontStr + "; font-size: 9px;";	
			if(ruleNo == "17") return defFontStr + "; font-size: 12px; font-weight: bold; color: #333333; background-color: #ECECEC";
			if(ruleNo == "18") return defFontStr + "; font-size: 12px; font-weight: bold; color: #FF0000; background-color: #ECECEC";
		}

		function getTitle() // Returns the correct document title
		{
			return title;
		}
		
		function setParentTitle(pTitle)
		{
			parentTitle = pTitle;
			return pTitle;
		}
		
		function getParentTitle()
		{
			return parentTitle;
		}	
		
		function sefForm(pForm)
		{
			formTitle = pForm;
			return pForm;
		}
		
		function getFormTitle()
		{
			return formTitle;
		}
				
		function getAlert(param) // Displays the appropriate alert message
		{
			// Vars
			var mes = new Array();

			mes[0] = "This is not a real file, the file is not a valid xml file, "
				+ "\\r\\nor a required node is missing.  This stylesheet only supports "
				+ "\\r\\nXML files that use correct WC3 XML syntax and conform to the "
				+ "\\r\\nDTD referenced in the selected file.  Please check the syntax "
				+ "\\r\\nand location of the selected file and try again.";
			mes[1] = "Your browser security settings do not permit this action.";
			mes[2] = "Node not found.  Check reference to FDA Regional instance.";
			mes[3] = "A reference to the US Regional XML file was not found in the eCTD backbone.  "
				+ "Using ";
			mes[4] = "File path is incorrect or file could not be found.\\r\\nPlease check the file path and try again.";

			if(param > (mes.length-1)) return "";

			return mes[param];

		}

		]]></msxsl:script>
		 <xsl:template name="string-replace-all">
     <xsl:param name="text" />
     <xsl:param name="replace" />
     <xsl:param name="by" />
     <xsl:choose>
       <xsl:when test="contains($text, $replace)">
         <xsl:value-of select="substring-before($text,$replace)" />
         <xsl:value-of select="$by" />
         <xsl:call-template name="string-replace-all">
           <xsl:with-param name="text"
          select="substring-after($text,$replace)" />
           <xsl:with-param name="replace" select="$replace" />
           <xsl:with-param name="by" select="$by" />
         </xsl:call-template>
       </xsl:when>
       <xsl:otherwise>
         <xsl:value-of select="$text" />
       </xsl:otherwise>
     </xsl:choose>
   </xsl:template>
	<xsl:template match="fda-regional:fda-regional">
		<!-- PROCESSING STARTS HERE -->
		<xsl:variable name="title" select="js:getTitle()"/>
		<table width="100%" border="0" cellspacing="0" summary="This table contains the title of the XML transformation">
			<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('1')"/></xsl:attribute>
			<tr>
				<td align="center" style="color=#564742">
					<!-- DOCUMENT TITLE -->
					<h2>
						<xsl:value-of select="$title"/>
					</h2>
				</td>
			</tr>
		</table>
		<table width="100%" bordercolor="#7B655F" border="1" cellspacing="0" summary="This table contains the XML instance summary information">
			<tr>
				<td>
					<table width="100%" border="0" cellspacing="0" cellpadding="4" bgcolor="white">
						<tr>
							<td>
								<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
							</td>
							<td>
								<table width="100%" border="0" cellspacing="0" cellpadding="2" bgcolor="white">
									<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('2')"/></xsl:attribute>
									<tr>
										<!-- SUMMARY INFORMATION (CUSTOMIZE AS NEEDED) -->
										<td valign="_top">
											<table width="100%" border="1" bordercolor="#564742">
												<tr>
													<th width="150px" bgcolor="#FEF4F0" style="color=#333333">Summary</th>
													<td>
														<table border="0">
															<tr>
																<td style="border:0;">Applicant Name:&#160;<xsl:value-of select="admin/applicant-info/company-name"/>
																</td>
															</tr>
															<tr>
																<td style="border:0;">Applicant Id:&#160;<xsl:value-of select="admin/applicant-info/id"/>
																</td>
															</tr>
															<xsl:choose>
																<xsl:when test="(string-length(/descendant::submission-description) &gt; 0) and (string-length(/descendant::submission-description) &lt; 129) and (descendant::submission-description != ' ')">
																	<tr>
																		<td style="border:0;">Description:&#160;<xsl:value-of select="descendant::submission-description"/>
																		</td>
																	</tr>
																</xsl:when>
																<xsl:otherwise>
																	<tr>
																		<td style="border:0;">
																			<xsl:variable name="summary_desc" select="/descendant::submission-description"/>
																			<xsl:value-of select="substring($summary_desc, 1, 128)"/>
																		</td>
																	</tr>
																</xsl:otherwise>
															</xsl:choose>
															<tr>
																<td style="border:0;">No. of Leaf Nodes:	<xsl:value-of select="count(descendant::leaf)"/>
																</td>
															</tr>
														</table>
													</td>
												</tr>
											</table>
											<p/>
											<table width="100%" border="1" bordercolor="#564742">
												<th width="150px" bgcolor="#FEF4F0" style="color=#333333">Contact Information</th>
												<td>
													<xsl:for-each select="admin/applicant-info/applicant-contacts/applicant-contact">
														<table width="100%" border="0" cellpadding="2">
															<tr>
																<td style="border:0;">Applicant Contact: <xsl:value-of select="applicant-contact-name"/>
																	<xsl:variable name="contact-type" select=".//applicant-contact-name/@applicant-contact-type"/>
																	<xsl:for-each select="document('applicant-contact-type.xml')/applicant-contact-type/code-display[@code]">
																		<xsl:variable name="contact-type-code" select="@code"/>
																		<xsl:if test="$contact-type = $contact-type-code">
														&#40;<xsl:value-of select="@display"/>&#41;
																</xsl:if>
																	</xsl:for-each>
																</td>
															</tr>
															<tr>
																<td style="border:0;">Contact Info: <xsl:apply-templates select=".//telephone"/>
																</td>
															</tr>
															<tr>
																<td style="border:0;">E-mail: <xsl:value-of select="substring(descendant::email,1, 64)"/>
																</td>
															</tr>
															<xsl:if test="position()!=last()">
																<tr>
																	<td style="border:0;">
																		<hr/>
																	</td>
																</tr>
															</xsl:if>
															<xsl:if test="position()=last()">
																<tr>
																	<td style="border:0;">
																		<p/>
																	</td>
																</tr>
															</xsl:if>
														</table>
													</xsl:for-each>
												</td>
											</table>
											<p/>
											<table width="100%" border="1" bordercolor="#564742">
												<th width="150px" valign="middle" bgcolor="#FEF4F0" style="color=#333333">Application Information</th>
												<td>
													<table width="100%" border="0">
														<xsl:for-each select="admin/application-set/application">
															<tr>
																<td>
																	<table width="100%" border="0" bordercolor="#564742" cellpadding="2">
																		<xsl:choose>
																			<xsl:when test="@application-containing-files='true' or @application-containing-files='false'">
																				<tr>
																					<td style="border:0;">Application Containing Files: <xsl:value-of select="@application-containing-files"/>
																					</td>
																				</tr>
																			</xsl:when>
																			<xsl:otherwise>
																				<tr>
																					<td style="border:0;">Application Containing Files: This value must be set to either true or false.
																			</td>
																				</tr>
																			</xsl:otherwise>
																		</xsl:choose>
																		<tr>
																			<td style="border:0;">Application Type:  <xsl:variable name="app-code" select=".//application-number/@application-type"/>
																				<xsl:for-each select="document('application-type.xml')/application-type/code-display[@code]">
																					<xsl:variable name="values" select="@code"/>
																					<xsl:if test="$app-code = $values">
																						<xsl:value-of select="@display"/>
																					</xsl:if>
																				</xsl:for-each>
																			</td>
																		</tr>
																		<tr>
																			<td style="border:0;">Application Number: <xsl:value-of select="descendant::application-number"/>
																			</td>
																		</tr>
																		<tr>
																			<td style="border:0;">Submission Type: <xsl:variable name="sub-code" select=".//submission-id/@submission-type"/>
																				<xsl:for-each select="document('submission-type.xml')/submission-type/code-display[@code]">
																					<xsl:variable name="values" select="@code"/>
																					<xsl:if test="$sub-code = $values">
																						<xsl:value-of select="@display"/>
																					</xsl:if>
																				</xsl:for-each>
																			</td>
																		</tr>
																		<xsl:if test="(string-length(/.//submission-id/@supplement-effective-date-type) &gt; 0) and (.//submission-id/@supplement-effective-date-type != ' ')">
																			<tr>
																				<td style="border:0;">Supplement Effective Date: <xsl:variable name="supplement-code" select=".//submission-id/@supplement-effective-date-type"/>
																					<xsl:for-each select="document('supplement-effective-date-type.xml')/supplement-effective-date-type/code-display[@code]">
																						<xsl:variable name="supp-code" select="@code"/>
																						<xsl:if test="$supplement-code = $supp-code">
																							<xsl:value-of select="@display"/>
																						</xsl:if>
																					</xsl:for-each>
																				</td>
																			</tr>
																		</xsl:if>
																		<tr>
																			<td style="border:0;">Submission Id: 	<xsl:value-of select="descendant::submission-id"/>
																			</td>
																		</tr>
																		<tr>
																			<td style="border:0;">Submission Sub-Type: <xsl:variable name="sub-type-code" select=".//sequence-number/@submission-sub-type"/>
																				<xsl:for-each select="document('submission-sub-type.xml')/submission-sub-type/code-display[@code]">
																					<xsl:variable name="values" select="@code"/>
																					<xsl:if test="$sub-type-code = $values">
																						<xsl:value-of select="@display"/>
																					</xsl:if>
																				</xsl:for-each>
																			</td>
																		</tr>
																		<tr>
																			<td style="border:0;">Sequence #: 	<xsl:value-of select='substring(format-number(descendant::sequence-number, "0000"),1, 4)'/>
																			</td>
																		</tr>
																		<xsl:if test="(string-length(/descendant::cross-reference-application-number) &gt; 0) and (descendant::cross-reference-application-number != ' ')">
																			<xsl:for-each select=".//cross-reference-application-number">
																				<tr>
																					<td style="border:0;">
																						Cross Reference Number: <xsl:value-of select="."/>
																					</td>
																				</tr>
																				<tr>
																					<td style="border:0;">
																						<xsl:variable name="cross-ref-code" select="@application-type"/>
																						<xsl:for-each select="document('application-type.xml')/application-type/code-display[@code]">
																							<xsl:variable name="values" select="@code"/>
																							<xsl:if test="$cross-ref-code = $values">
																							Cross Reference Type: <xsl:value-of select="@display"/>
																							</xsl:if>
																						</xsl:for-each>
																					</td>
																				</tr>
																			</xsl:for-each>
																		</xsl:if>
																		<xsl:if test="position()!=last()">
																			<tr>
																				<td style="border:0;">
																					<hr/><!--Adds horizontal line between each application in the application set-->
																				</td>
																			</tr>
																		</xsl:if>
																		<xsl:if test="position()=last()">
																			<tr>
																				<td style="border:0;">
																					<p/>
																				</td>
																			</tr>
																		</xsl:if>
																	</table>
																</td>
															</tr>
														</xsl:for-each>
													</table>
												</td>
											</table>
										</td>
									</tr>
								</table>
							</td>
						</tr>
					</table>
				</td>
			</tr>
		</table>
		<br/>
		<table align="center" width="100" border="0" cellspacing="0" summary="This table contains controls for displaying and hiding all document summaries">
			<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('1')"/></xsl:attribute>
			<tr>
				<td align="center">
					<input name="expandAll" type="button" value="Expand All" accesskey="e" title="Expand all document summaries">
						<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('10')"/></xsl:attribute>
						<xsl:attribute name="ONCLICK">    <!--attribute name and code for ONCLICK feature + and - for leaf-->
								var div=document.getElementsByTagName("div");
						
								for(i=0;i&lt;div.length;i++)
								{
									var divName = div[i].name;
									if(divName != null &amp;&amp; divName == "showData")
									{
										var a1=div[i].parentNode.firstChild.nextSibling.nextSibling;
										div[i].style.display="block";
										a1.title = "Collapse document summary";
									}
									if(divName != null &amp;&amp; divName == "expand")
									{
										div[i].style.display="none";
									}
									if(divName != null &amp;&amp; divName == "collapse")
									{
										div[i].style.display="inline";
									}
								}
								return false;
							</xsl:attribute>
					</input>
				</td>
				<td align="center">
					<input name="collapseAll" type="button" value="Collapse All" accesskey="c" title="Collapse all document summaries">
						<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('10')"/></xsl:attribute>
						<xsl:attribute name="ONCLICK">
								var div=document.getElementsByTagName("div");
								for(i=0;i&lt;div.length;i++)
								{
									var divName = div[i].name;
									if(divName != null &amp;&amp; divName == "showData")
									{
										var a1=div[i].parentNode.firstChild.nextSibling.nextSibling;
										div[i].style.display="none";
										a1.title = "Expand document summary";
									}
									if(divName != null &amp;&amp; divName == "expand")
									{
										div[i].style.display="inline";
									}
									if(divName != null &amp;&amp; divName == "collapse")
									{
										div[i].style.display="none";
									}
								}
								return false;
							</xsl:attribute>
					</input>
				</td>
			</tr>
		</table>
		<br/>
		<xsl:if test="descendant::form">
			<table width="100%" border="1" bordercolor="#787878" cellspacing="0" cellpadding="4" bgcolor="white" summary="This table contains the title of a section">
				<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule(5)"/></xsl:attribute>
				<tr>
					<td>&#160;&#160;&#160;m1-1-forms</td>
				</tr>
				<xsl:for-each select="descendant::form">
					<xsl:variable name="unique" select="not(@form-type=preceding::form/@form-type)"/>
					<tr>
						<td style="border:0;">
							<xsl:variable name="form-list" select="@form-type"/>
							<xsl:for-each select="document('form-type.xml')/form-type/code-display">
								<xsl:if test="($form-list = @code) and (@code = $unique)">
									<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule(17)"/></xsl:attribute>
								&#160;&#160;&#160;&#160;<xsl:value-of select="@display"/>
								</xsl:if>
							</xsl:for-each>
							<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule(17)"/></xsl:attribute>
							<xsl:apply-templates select="leaf"/>
						</td>
					</tr>
				</xsl:for-each>
			</table>
		</xsl:if>
		<xsl:for-each select="descendant::node()">
			<xsl:if test="(contains(name(),'m1-2-')
	or contains(name(),'m1-3-') or contains(name(),'m1-4-') or contains(name(),'m1-5-') or contains(name(),'m1-6-') or contains(name(),'m1-7-') or contains(name(),'m1-8-') or contains(name(),'m1-9-') or contains(name(),'m1-10-') or contains(name(),'m1-11-') or contains(name(),'m1-12-') or contains(name(),'m1-13-') or contains(name(),'m1-14-'))">
				<xsl:if test="leaf | node-extension/leaf | node-extension/node-extension/leaf">
					<xsl:if test="leaf">
						<br/>
						<table width="100%" border="1" bordercolor="#787878" cellspacing="0" cellpadding="0" bgcolor="#787878" summary="This table contains the border for a section">
							<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule(0)"/></xsl:attribute>
							<tr>
								<td>
									<table width="100%" border="0" cellspacing="0" cellpadding="4" bgcolor="white" summary="This table contains background for a section">
										<tr>
											<td>
												<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
												<table width="100%" border="0" bordercolor="black" cellspacing="0" cellpadding="2" bgcolor="white" summary="This table contains the title of a section">
													<tr>
														<td height="10">
																		</td>
													</tr>
												</table>
											</td>
											<td valign="center">
												<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('5')"/></xsl:attribute>
												<xsl:choose>
													<xsl:when test="../node-extension">
														<xsl:value-of select="js:getParentTitle()"/>
														<xsl:for-each select="../node-extension">
																			-&#160;<xsl:value-of select="title"/>
														</xsl:for-each>
													</xsl:when>
													<xsl:otherwise>
														<xsl:variable name="module-title">
															<xsl:if test="not(ancestor::m1-15-promotional-material)">
																<xsl:value-of select="name()"/>
																<xsl:for-each select="@indication">-<xsl:value-of select="."/>
																</xsl:for-each>
																<xsl:for-each select="@manufacturer">-<xsl:value-of select="."/>
																</xsl:for-each>
																<xsl:for-each select="@substance">-<xsl:value-of select="."/>
																</xsl:for-each>
																<xsl:for-each select="@dosageform">-<xsl:value-of select="."/>
																</xsl:for-each>
																<xsl:for-each select="@product-name">-<xsl:value-of select="."/>
																</xsl:for-each>
															</xsl:if>
														</xsl:variable>
														<xsl:value-of select="js:setParentTitle($module-title)"/>
													</xsl:otherwise>
												</xsl:choose>
											</td>
										</tr>
									</table>
								</td>
							</tr>
						</table>
						<xsl:apply-templates select="leaf"/>
					</xsl:if>
				</xsl:if>
			</xsl:if>
		</xsl:for-each>
		<xsl:if test="descendant::m1-15-promotional-material">
			<br/>
			<style>
				span{ color:red; }
			</style>
			<table width="100%" border="1" bordercolor="#787878" cellspacing="0" cellpadding="3" bgcolor="white" summary="This table contains the title of a section">
				<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule(5)"/></xsl:attribute>
				<xsl:for-each select="descendant::m1-15-promotional-material">
					<tr>
						<td colspan="5">
							<xsl:variable name="promotional-material" select="@promotional-material-audience-type"/>
							<xsl:for-each select="document('promotional-material-audience-type.xml')/promotional-material-audience-type/code-display">
								<xsl:variable name="values" select="@code"/>
								<xsl:if test="($promotional-material = $values)">				
					&#160;&#160;&#160;m1-15-promotional-material&#160;<span>&#40;<xsl:value-of select="@display"/>&#41;</span>
								</xsl:if>
							</xsl:for-each>
						</td>
					</tr>
					<xsl:for-each select="child::node()">
						<tr>
							<td style="border:0;">
								<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
							</td>
							<td style="border:0;" colspan="4">
								<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
								<xsl:value-of select="normalize-space(name())"/>
								<xsl:if test="self::m1-15-2-materials">
									<xsl:variable name="material-doc-type" select="@promotional-material-doc-type"/>
									<xsl:for-each select="document('promotional-material-doc-type.xml')/promotional-material-doc-type/code-display">
										<xsl:variable name="material-doc-code" select="@code"/>
										<xsl:if test="($material-doc-type = $material-doc-code)">
											&#160;<span>&#40;<xsl:value-of select="@display"/>&#41;</span>
										</xsl:if>
									</xsl:for-each>
								</xsl:if>
							</td>
						</tr>
						<xsl:for-each select="child::node()">
							<tr>
								<td style="border:0;">
									<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
								</td>
								<td style="border:0;">
									<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
								</td>
								<td style="border:0;" colspan="3">
									<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
									<xsl:value-of select="normalize-space(name())"/>
									<xsl:if test="ancestor::m1-15-1-correspondence-relating-to-promotional-materials">
											<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
											<xsl:apply-templates select="leaf"/>
								</xsl:if>
									<xsl:if test="ancestor::m1-15-2-materials">
										<xsl:variable name="id-type" select="@promotional-material-type"/>
										<xsl:variable name="material-id-str" select="@material-id"/>
										<xsl:variable name="date-str" select="@issue-date"/>
										
										<!--Set-up date format yyyymmdd-->
										<xsl:variable name="dd">
											<xsl:value-of select="substring($date-str,5,4)" />
										</xsl:variable>
										<xsl:variable name="mm">
											<xsl:value-of select="substring($date-str,3,2)" />
										</xsl:variable>
										<xsl:variable name="yyyy">
											<xsl:value-of select="substring($date-str,1,2)" />
										</xsl:variable>
										
										<xsl:for-each select="document('promotional-material-type.xml')/promotional-material-type/code-display">
											<xsl:variable name="material-id-code" select="@code"/>
											<xsl:if test="($id-type = $material-id-code)">
                                                &#160;<span>&#40;<xsl:value-of select="@display"/>&#41;</span>
                                                <xsl:if test="string-length($material-id-str) &lt; 31">
													&#160;&#160;material-id&#160;<span><xsl:value-of select="$material-id-str"/></span>
                                                </xsl:if>
                                                <xsl:if test="string-length($material-id-str) &gt; 30"> <!--Truncate string to 30 characters-->
													&#160;&#160;material-id&#160;<span><xsl:value-of select="substring($material-id-str,0,31)"/></span>
                                                </xsl:if>
                                              
                                                <xsl:if test="string-length($date-str) &gt; 0 and string-length($date-str) &lt; 9">
													&#160;&#160;issue-date&#160;<span><xsl:value-of select="$yyyy"/><xsl:value-of select="$mm"/><xsl:value-of select="$dd"/></span>
                                                </xsl:if>
													
											</xsl:if>
										</xsl:for-each>
									</xsl:if>
								</td>
							</tr>
								<xsl:for-each select="child::node()">
								<xsl:if test="ancestor::m1-15-2-materials">
									<tr>
										<td style="border:0;">
											<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
										</td>
										<td style="border:0;">
											<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
										</td>
										<td style="border:0;" colspan="3">
											<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
																			&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;<xsl:value-of select="normalize-space(name())"/>
											<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('9')"/></xsl:attribute>
											<xsl:apply-templates select="leaf"/>
										</td>
									</tr>
								</xsl:if>
							</xsl:for-each>
						</xsl:for-each>
					</xsl:for-each>
				</xsl:for-each>
			</table>
		</xsl:if>
		<xsl:if test="descendant::m1-16-risk-management-plan">
		<br/>
			<style>
				span{ color:red; }
			</style>
			<table width="100%" border="1" bordercolor="#787878" cellspacing="0" cellpadding="3" bgcolor="white" summary="This table contains the title of a section">
				<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule(5)"/></xsl:attribute>
				<xsl:for-each select="descendant::m1-16-risk-management-plan">
					<tr>
						<td colspan="5">			
					&#160;&#160;&#160;m1-16-risk-management-plan&#160;
						</td>
					</tr>					
					<xsl:for-each select="child::node()">
							<tr>
								<td style="border:0;" colspan="3">	
									<xsl:if test="self::m1-16-1-risk-management-non-rems">
										<tr>
										<td style="border:0;">
											<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
												&#160;&#160;&#160;&#160;&#160;<xsl:value-of select="normalize-space(name())"/>
												<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('9')"/></xsl:attribute>
												<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute><xsl:apply-templates select="leaf"/>
											</td>
										</tr>
									</xsl:if>
									<xsl:if test="self::m1-16-2-risk-evaluation-and-mitigation-strategies-rems">
										<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
												&#160;&#160;&#160;&#160;&#160;<xsl:value-of select="name()"/>
										<xsl:for-each select="child::node()">
											<xsl:if test="ancestor::m1-16-2-risk-evaluation-and-mitigation-strategies-rems">
												<tr>
												<td style="border:0;">
													<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('17')"/></xsl:attribute>
														&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;<xsl:value-of select="normalize-space(name())"/>
														<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('9')"/></xsl:attribute>
														<xsl:apply-templates select="leaf"/>
													</td>
												</tr>
											</xsl:if>
										</xsl:for-each>
									</xsl:if>
								</td>
							</tr>
							</xsl:for-each>
				</xsl:for-each>
			</table>
		</xsl:if>
		<xsl:for-each select="descendant::node()">
			<xsl:if test="contains(name(),'m1-17-') or contains(name(),'m1-18-') or contains(name(),'m1-19-') or contains(name(),'m1-20-')
				or contains(name(),'m2-')
					or contains(name(),'m3-')
						or contains(name(),'m4-')
							or contains(name(),'m5-')">
				<xsl:if test="leaf | node-extension/leaf | node-extension/node-extension/leaf">
					<xsl:if test="leaf">
						<br/>
						<table width="100%" border="1" bordercolor="#787878" cellspacing="0" cellpadding="0" bgcolor="#787878" summary="This table contains the border for a section">
							<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule(0)"/></xsl:attribute>
							<tr>
								<td>
									<table width="100%" border="0" cellspacing="0" cellpadding="4" bgcolor="white" summary="This table contains background for a section">
										<tr>
											<td>
												<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
												<table width="100%" border="0" bordercolor="black" cellspacing="0" cellpadding="2" bgcolor="white" summary="This table contains the title of a section">
													<tr>
														<td height="10">
																		</td>
													</tr>
												</table>
											</td>
											<td valign="center">
												<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('5')"/></xsl:attribute>
												<xsl:choose>
													<xsl:when test="../node-extension">
														<xsl:value-of select="js:getParentTitle()"/>
														<xsl:for-each select="../node-extension">
																			-&#160;<xsl:value-of select="title"/>
														</xsl:for-each>
													</xsl:when>
													<xsl:otherwise>
														<xsl:variable name="module-title">
															<xsl:if test="not(ancestor::m1-15-promotional-material)">
																<xsl:value-of select="name()"/>
																<xsl:for-each select="@indication">-<xsl:value-of select="."/>
																</xsl:for-each>
																<xsl:for-each select="@manufacturer">-<xsl:value-of select="."/>
																</xsl:for-each>
																<xsl:for-each select="@substance">-<xsl:value-of select="."/>
																</xsl:for-each>
																<xsl:for-each select="@dosageform">-<xsl:value-of select="."/>
																</xsl:for-each>
																<xsl:for-each select="@product-name">-<xsl:value-of select="."/>
																</xsl:for-each>
															</xsl:if>
														</xsl:variable>
														<xsl:value-of select="js:setParentTitle($module-title)"/>
													</xsl:otherwise>
												</xsl:choose>
											</td>
										</tr>
									</table>
								</td>
							</tr>
						</table>
						<xsl:apply-templates select="leaf"/>
					</xsl:if>
				</xsl:if>
			</xsl:if>
		</xsl:for-each>
	</xsl:template>
	<xsl:template match="telephone">
		<xsl:value-of select="substring(self::telephone,1, 64)"/>
		<xsl:variable name="tel-type" select="@telephone-number-type"/>
		<xsl:for-each select="document('telephone-number-type.xml')/telephone-number-type/code-display">
			<xsl:variable name="tel-type-values" select="@code"/>
			<xsl:if test="$tel-type = $tel-type-values">
				&#40;<xsl:value-of select="@display"/>&#41;&#160;
			</xsl:if>
		</xsl:for-each>
	</xsl:template>
	<xsl:template match="leaf">
		<xsl:for-each select=".">
			<!-- THIS HANDLES LEAVES AT THREE LEVELS -->
			<xsl:if test="@operation | @xlink:type">
				<table width="100%" border="0" cellspacing="0" cellpadding="4" bgcolor="#ECECEC" summary="This table contains the title of a document">
					<tr>
						<td>
							<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
						</td>
						<td>
							<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
						</td>
						<td>
							<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
						</td>
						<xsl:if test="ancestor::m1-16-1-risk-management-non-rems">
							<td>
								<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
							</td>
						</xsl:if>
						<xsl:if test="ancestor::m1-15-2-materials or ancestor::m1-16-2-risk-evaluation-and-mitigation-strategies-rems">
							<td>
								<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
							</td>
							<td>
								<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
							</td>
							<td>
								<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
							</td>
							<td>
								<xsl:attribute name="WIDTH"><xsl:value-of select="js:getIndent()"/></xsl:attribute>
							</td>
						</xsl:if>
						<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('6')"/></xsl:attribute>
						<td align="left">
							<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('6')"/>></xsl:attribute>
							<a title="Open a secondary window that displays the indicated file" style="text-decoration: none">
								<!-- OPENS A DOCUMENT -->
								<xsl:variable name="myVar">
     <xsl:call-template name="string-replace-all">
       <xsl:with-param name="text" select="@xlink:href" />
       <xsl:with-param name="replace" select="'\'" />
       <xsl:with-param name="by" select="'\\'" />
     </xsl:call-template>
   </xsl:variable>
								<xsl:attribute name="HREF"/>
								<xsl:attribute name="ONCLICK">
																
																// Vars
																var check = "";
																var displayFile = "";
																var displayLoc = "";
fileName = "<xsl:value-of select="$myVar"/>";																													var loads = null;
																var openLoc = null;
																var redundant = false;
																var selLoc = null;
																var sep = "/";
																var styleSheet = null;
																var subDirPath = null;
																var type = null;
																var xml = null;
																var style = null;
																var win = null;
																var winHeight = 0.70*window.screen.height;
																var winWidth = 0.75*window.screen.width;
																							
																openLoc = this.document.URL;
																if(openLoc != null &amp;&amp; openLoc.indexOf("\\") > -1) {
																	openLoc = openLoc.substring(0,openLoc.lastIndexOf("\\"));
																}
																			
																else
																{
																	if(openLoc != null &amp;&amp; openLoc.indexOf("/") > -1) {        <!--Parse URL Paths that use forward slashes -->
																		openLoc = openLoc.substring(0,openLoc.lastIndexOf("/"));}
																}
																																														
																if(fileName.indexOf("/") == -1)
																{
{																	sep = "\\";																}
}																
																check = fileName; // Set the directory name holder
																check = check.substring(0,check.lastIndexOf(sep));
							
																if(subDirPath == null)
																{
																	subDirPath = check;
																}
							
																while(check.indexOf(sep) &gt; -1) // Make sure URL pieces are unique
																{
																	check = check.substring(0,check.lastIndexOf(sep));
																	
																	if(openLoc.indexOf(check) &gt; 0 &amp;&amp;
																		!redundant) // Remove directory name overlap
																	{
																		fileName = fileName.substring(0,fileName.indexOf(check)-1);
																		redundant = true;
																	}
										
																}
																
																if(subDirPath != null &amp;&amp; selLoc != null &amp;&amp; selLoc.indexOf(subDirPath) &lt; 0)
																{
																	openLoc += sep + subDirPath;
																}
							
																if(!redundant)
																{
																	selLoc = openLoc + "\\" + fileName;
																}
															
																if(fileName != "") // If there is a file name, parse
																{
																	if(selLoc != "") {
																		try {
																			window.open(selLoc,"","alwaysRaised=yes,scrollbars=yes,menubar=yes,toolbar=yes,location=yes,status=yes,"
																				+ "resizable=yes,width=" + winWidth + ",height=" + winHeight+ ",left=120,top=50");
																		} catch(e) {
																			alert("<xsl:value-of select="js:getAlert(4)"/>");
																		}
																	} else {
																		alert("<xsl:value-of select="js:getAlert(4)"/>");
																	}
																}
																
																return false;
							
															</xsl:attribute>
								<xsl:choose>
									<xsl:when test="title and string-length(title) > 0">
										<xsl:value-of select="title"/>
									</xsl:when>
									<xsl:otherwise>No Title</xsl:otherwise>
								</xsl:choose>
								<font color="red">&#160;&#91;<xsl:value-of select="@operation"/>&#93;</font> <!--contains operation with brackets in red-->
							</a>
							<a name="summary" href="" title="Expand document summary">
								<!-- EXPANDS A SUMMARY -->
								<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('14')"/></xsl:attribute>
								<xsl:attribute name="ONCLICK">
																if (this.nextSibling.style.display=="block")
																{
																	this.nextSibling.style.display="none";
																	this.title = "Expand document summary";
																	this.firstChild.style.display="inline";
																	this.firstChild.nextSibling.style.display="none";
																}
																else
																{
																	this.nextSibling.style.display="block";
																	this.title = "Collapse document summary";
																	this.firstChild.style.display="none";
																	this.firstChild.nextSibling.style.display="inline";
																}
																return false;
															</xsl:attribute>
								<div name="expand" style="position:relative; display=inline;">&#160;+</div>
								<div name="collapse" style="position:relative; display=none;">&#160;-</div>
							</a>
							<!-- ADD FILE ATTRIBUTE VALUE NAME CHECKS HERE -->
							<div name="showData" style="position:relative; display=none;">
								<xsl:attribute name="STYLE"><xsl:value-of select="js:getCSSRule('9')"/></xsl:attribute>
								<xsl:attribute name="ID"><xsl:value-of select="js:getUnique()"/></xsl:attribute>
								<xsl:if test="@actuate"> 
															&#160;Actuate = <xsl:value-of select="@actuate"/>
									<br/>
								</xsl:if>
															&#160;Application Version = <xsl:value-of select="@application-version"/>
								<br/>
															&#160;Checksum = <xsl:value-of select="@checksum"/>
								<xsl:value-of select="@md5-checksum"/>
								<br/>
															&#160;Checksum Type = <xsl:value-of select="@checksum-type"/>
								<br/>
															&#160;Filename = <xsl:value-of select="@xlink:href"/>
								<br/>
															&#160;Font Library = <xsl:value-of select="@font-library"/>
								<br/>
															&#160;ID = <xsl:value-of select="@ID"/>
								<xsl:value-of select="@id"/>
								<br/>
															&#160;Keywords = <xsl:value-of select="@keywords"/>
								<br/>
								<xsl:if test="@lang"> 
															&#160;Language = <xsl:value-of select="@lang"/>
									<br/>
								</xsl:if>
								<xsl:if test="@modified-file"> &#160;Modified File = <xsl:value-of select="@modified-file"/>
									<br/>
								</xsl:if>
															&#160;Operation = <xsl:value-of select="@operation"/>
								<br/>
								<xsl:if test="@xlink:role"> 
															&#160;Role = <xsl:value-of select="@xlink:role"/>
									<br/>
								</xsl:if>
								<xsl:if test="@xlink:show"> 
															&#160;Show = <xsl:value-of select="@xlink:show"/>
									<br/>
								</xsl:if>
															&#160;Version = <xsl:value-of select="@version"/>
								<br/>
							</div>
						</td>
					</tr>
				</table>
			</xsl:if>
		</xsl:for-each>
	</xsl:template>
</xsl:stylesheet>
